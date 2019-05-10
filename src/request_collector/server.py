import sys

import gevent
import structlog
from eth_utils import encode_hex, to_checksum_address

from monitoring_service.database import SharedDatabase
from monitoring_service.states import MonitorRequest
from raiden.constants import MONITORING_BROADCASTING_ROOM
from raiden.exceptions import InvalidSignature
from raiden.messages import Message, RequestMonitoring
from raiden_libs.gevent_error_handler import register_error_handler
from raiden_libs.matrix import MatrixListener

log = structlog.get_logger(__name__)


class RequestCollector(gevent.Greenlet):
    def __init__(self, private_key: str, state_db: SharedDatabase):
        super().__init__()

        self.private_key = private_key
        self.state_db = state_db

        state = self.state_db.load_state()
        self.chain_id = state.blockchain_state.chain_id
        self.matrix_listener = MatrixListener(
            private_key=private_key,
            chain_id=self.chain_id,
            service_room_suffix=MONITORING_BROADCASTING_ROOM,
            message_received_callback=self.handle_message,
        )

    def listen_forever(self) -> None:
        self.matrix_listener.listen_forever()

    def _run(self) -> None:  # pylint: disable=method-hidden
        register_error_handler()

        try:
            self.matrix_listener.start()
        except ConnectionError as exc:
            log.critical("Could not connect to broadcasting system.", exc=exc)
            sys.exit(1)

    def stop(self) -> None:
        self.matrix_listener.stop()
        self.matrix_listener.join()

    def handle_message(self, message: Message) -> None:
        if isinstance(message, RequestMonitoring):
            self.on_monitor_request(message)
        else:
            log.info("Ignoring unknown message type")

    def on_monitor_request(self, request_monitoring: RequestMonitoring) -> None:
        assert isinstance(request_monitoring, RequestMonitoring)

        # Convert Raiden's RequestMonitoring object to a MonitorRequest
        try:
            monitor_request = MonitorRequest(
                channel_identifier=request_monitoring.balance_proof.channel_identifier,
                token_network_address=to_checksum_address(
                    request_monitoring.balance_proof.token_network_address
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
            log.info("Ignore MR with invalid signature", monitor_request=request_monitoring)
            return

        # Validate MR
        if monitor_request.chain_id != self.chain_id:
            log.debug("Bad chain_id", monitor_request=monitor_request, expected=self.chain_id)
            return

        # Check that received MR is newer by comparing nonces
        old_mr = self.state_db.get_monitor_request(
            token_network_address=monitor_request.token_network_address,
            channel_id=monitor_request.channel_identifier,
            non_closing_signer=monitor_request.non_closing_signer,
        )
        if old_mr and old_mr.nonce >= monitor_request.nonce:
            log.debug(
                "New MR does not have a newer nonce.",
                token_network_address=monitor_request.token_network_address,
                channel_identifier=monitor_request.channel_identifier,
                received_nonce=monitor_request.nonce,
                known_nonce=old_mr.nonce,
            )
            return

        log.info(
            "Received new MR",
            token_network_address=monitor_request.token_network_address,
            channel_identifier=monitor_request.channel_identifier,
            nonce=monitor_request.nonce,
            signer=monitor_request.signer,
            non_closing_signer=monitor_request.non_closing_signer,
            reward_signer=monitor_request.reward_proof_signer,
            reward_amount=monitor_request.reward_amount,
        )

        with self.state_db.conn:
            self.state_db.upsert_monitor_request(monitor_request)
