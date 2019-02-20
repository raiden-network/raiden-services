import sys
import traceback

import gevent
import structlog
from eth_utils import encode_hex, to_checksum_address

from monitoring_service.database import SharedDatabase
from monitoring_service.states import MonitorRequest
from raiden.constants import MONITORING_BROADCASTING_ROOM
from raiden.messages import RequestMonitoring, SignedMessage
from raiden_libs.exceptions import InvalidSignature
from raiden_libs.gevent_error_handler import register_error_handler
from raiden_libs.matrix import MatrixListener

log = structlog.get_logger(__name__)


def error_handler(_context, exc_info):
    log.critical("Unhandled exception terminating the program")
    traceback.print_exception(
        etype=exc_info[0],
        value=exc_info[1],
        tb=exc_info[2],
    )
    sys.exit()


class RequestCollector(gevent.Greenlet):
    def __init__(
        self,
        private_key: str,
        state_db: SharedDatabase,
    ):
        super().__init__()

        self.private_key = private_key
        self.state_db = state_db

        state = self.state_db.load_state(0)
        try:
            self.matrix_listener = MatrixListener(
                private_key=private_key,
                chain_id=state.blockchain_state.chain_id,
                callback=self.handle_message,
                service_room_suffix=MONITORING_BROADCASTING_ROOM
            )
        except ConnectionError as e:
            log.critical(
                'Could not connect to broadcasting system.',
                exc=e,
            )
            sys.exit(1)

    def _run(self):
        register_error_handler(error_handler)

        self.matrix_listener.run()

    def stop(self):
        self.matrix_listener.stop()
        self.matrix_listener.join()

    def handle_message(self, message: SignedMessage):
        if isinstance(message, RequestMonitoring):
            self.on_monitor_request(message)
        else:
            log.info('Ignoring unknown message type')

    def on_monitor_request(
        self,
        request_monitoring: RequestMonitoring,
    ):
        assert isinstance(request_monitoring, RequestMonitoring)

        # Convert Raiden's RequestMonitoring object to a MonitorRequest
        try:
            monitor_request = MonitorRequest(
                channel_identifier=request_monitoring.balance_proof.channel_identifier,
                token_network_address=to_checksum_address(
                    request_monitoring.balance_proof.token_network_address,
                ),
                chain_id=request_monitoring.balance_proof.chain_id,
                balance_hash=encode_hex(request_monitoring.balance_proof.balance_hash),
                nonce=request_monitoring.balance_proof.nonce,
                additional_hash=encode_hex(request_monitoring.balance_proof.additional_hash),
                closing_signature=encode_hex(request_monitoring.balance_proof.signature),
                non_closing_signature=encode_hex(request_monitoring.non_closing_signature),
                reward_amount=request_monitoring.reward_amount,
                reward_proof_signature=encode_hex(request_monitoring.signature),
            )
        except InvalidSignature:
            log.info(
                'Ignore MR with invalid signature',
                monitor_request=request_monitoring,
            )
            return

        # Check that received MR is newer by comparing nonces
        old_mr = self.state_db.get_monitor_request(
            token_network_address=monitor_request.token_network_address,
            channel_id=monitor_request.channel_identifier,
            non_closing_signer=monitor_request.non_closing_signer,
        )
        if old_mr and old_mr.nonce >= monitor_request.nonce:
            log.debug(
                'New MR does not have a newer nonce.',
                token_network_address=monitor_request.token_network_address,
                channel_identifier=monitor_request.channel_identifier,
                received_nonce=monitor_request.nonce,
                known_nonce=old_mr.nonce,
            )
            return

        log.debug(
            'Received new MR',
            token_network_address=monitor_request.token_network_address,
            channel_identifier=monitor_request.channel_identifier,
            nonce=monitor_request.nonce,
            signer=monitor_request.signer,
            non_closing_signer=monitor_request.non_closing_signer,
            reward_signer=monitor_request.reward_proof_signer,
        )

        with self.state_db.conn:
            self.state_db.upsert_monitor_request(monitor_request)
