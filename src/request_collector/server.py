import sys

import gevent
import structlog
from eth_utils import encode_hex
from gevent import Timeout
from sentry_sdk import configure_scope

from monitoring_service.constants import CHANNEL_CLOSE_MARGIN
from monitoring_service.database import SharedDatabase
from monitoring_service.states import MonitorRequest
from raiden.constants import DeviceIDs
from raiden.exceptions import InvalidSignature
from raiden.messages.abstract import Message
from raiden.messages.monitoring_service import RequestMonitoring
from raiden.utils.typing import List, Optional, TokenNetworkAddress
from raiden_contracts.utils.type_aliases import PrivateKey
from raiden_libs.constants import MATRIX_START_TIMEOUT
from raiden_libs.matrix import MatrixListener

log = structlog.get_logger(__name__)


class RequestCollector(gevent.Greenlet):
    def __init__(
        self,
        private_key: PrivateKey,
        state_db: SharedDatabase,
        matrix_servers: Optional[List[str]] = None,
    ):
        super().__init__()

        self.private_key = private_key
        self.state_db = state_db

        state = self.state_db.load_state()
        self.chain_id = state.blockchain_state.chain_id
        self.matrix_listener = MatrixListener(
            private_key=private_key,
            chain_id=self.chain_id,
            device_id=DeviceIDs.MS,
            message_received_callback=self.handle_message,
            servers=matrix_servers,
        )

    def listen_forever(self) -> None:
        self.matrix_listener.run()

    def _run(self) -> None:  # pylint: disable=method-hidden
        try:
            self.matrix_listener.start()
            self.matrix_listener.startup_finished.wait(timeout=MATRIX_START_TIMEOUT)
        except (Timeout, ConnectionError) as exc:
            log.critical("Could not connect to broadcasting system.", exc=exc)
            sys.exit(1)

    def stop(self) -> None:
        self.matrix_listener.stop()
        self.matrix_listener.get()

    def handle_message(self, message: Message) -> None:
        with configure_scope() as scope:
            scope.set_extra("message", message)
            try:
                if isinstance(message, RequestMonitoring):
                    self.on_monitor_request(message)
                else:
                    log.debug("Ignoring message", message=message)
            # add more advanced exception catching
            except AssertionError as ex:
                log.error("Error while handling message", message=message, _exc=ex)

    def on_monitor_request(self, request_monitoring: RequestMonitoring) -> None:
        assert isinstance(request_monitoring, RequestMonitoring)
        assert request_monitoring.non_closing_signature is not None
        assert request_monitoring.reward_proof_signature is not None

        # Convert Raiden's RequestMonitoring object to a MonitorRequest
        try:
            monitor_request = MonitorRequest(
                channel_identifier=request_monitoring.balance_proof.channel_identifier,
                token_network_address=TokenNetworkAddress(
                    request_monitoring.balance_proof.token_network_address
                ),
                chain_id=request_monitoring.balance_proof.chain_id,
                balance_hash=encode_hex(request_monitoring.balance_proof.balance_hash),
                nonce=request_monitoring.balance_proof.nonce,
                additional_hash=encode_hex(request_monitoring.balance_proof.additional_hash),
                closing_signature=request_monitoring.balance_proof.signature,
                non_closing_signature=request_monitoring.non_closing_signature,
                reward_amount=request_monitoring.reward_amount,
                non_closing_participant=request_monitoring.non_closing_participant,
                reward_proof_signature=request_monitoring.signature,
                msc_address=request_monitoring.monitoring_service_contract_address,
            )
        except InvalidSignature:
            log.info("Ignore MR with invalid signature", monitor_request=request_monitoring)
            return

        # Validate MR
        if monitor_request.chain_id != self.chain_id:
            log.debug("Bad chain_id", monitor_request=monitor_request, expected=self.chain_id)
            return
        if monitor_request.non_closing_signer != monitor_request.non_closing_participant:
            log.info("MR not signed by non_closing_participant", monitor_request=monitor_request)
            return
        if monitor_request.non_closing_signer != monitor_request.reward_proof_signer:
            log.debug("The two MR signatures don't match", monitor_request=monitor_request)
            return

        # Ignore MRs for channels that are already closed for a while.
        # We need to do this to prevent clients from wasting the MS' gas by
        # updating the BP after the MS has already called `monitor`, see
        # https://github.com/raiden-network/raiden-services/issues/504.
        close_age = self.state_db.channel_close_age(
            token_network_address=monitor_request.token_network_address,
            channel_id=monitor_request.channel_identifier,
        )
        # This is x blocks after that event is already confirmed, so that should be plenty!
        if close_age is not None and close_age >= CHANNEL_CLOSE_MARGIN:
            log.warning(
                "Ignore MR for long closed channel",
                monitor_request=monitor_request,
                close_age=close_age,
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

        self.state_db.upsert_monitor_request(monitor_request)
