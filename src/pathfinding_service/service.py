import collections
import sys
import time
from dataclasses import asdict
from typing import Dict, Iterator, List, Optional

import gevent
import sentry_sdk
import structlog
from eth_utils import to_canonical_address
from gevent import Timeout
from web3 import Web3
from web3.contract import Contract

from pathfinding_service import metrics
from pathfinding_service.database import PFSDatabase
from pathfinding_service.exceptions import (
    InvalidCapacityUpdate,
    InvalidFeeUpdate,
    InvalidGlobalMessage,
)
from pathfinding_service.model import IOU, TokenNetwork
from pathfinding_service.model.channel import Channel
from pathfinding_service.typing import DeferableMessage
from raiden.constants import UINT256_MAX, DeviceIDs
from raiden.messages.abstract import Message
from raiden.messages.path_finding_service import PFSCapacityUpdate, PFSFeeUpdate
from raiden.utils.typing import BlockNumber, BlockTimeout, ChainID, TokenNetworkAddress
from raiden_contracts.constants import CONTRACT_TOKEN_NETWORK_REGISTRY, CONTRACT_USER_DEPOSIT
from raiden_contracts.utils.type_aliases import PrivateKey
from raiden_libs.blockchain import get_blockchain_events_adaptive
from raiden_libs.constants import MATRIX_START_TIMEOUT
from raiden_libs.events import (
    Event,
    ReceiveChannelClosedEvent,
    ReceiveChannelOpenedEvent,
    ReceiveTokenNetworkCreatedEvent,
    UpdatedHeadBlockEvent,
)
from raiden_libs.matrix import MatrixListener
from raiden_libs.states import BlockchainState
from raiden_libs.utils import private_key_to_address

log = structlog.get_logger(__name__)


class DeferMessage(Exception):
    """Stop processing the message and handle it when the channel has been opened"""

    deferred_message: DeferableMessage

    def __init__(self, deferred_message: DeferableMessage):
        super().__init__()
        self.deferred_message = deferred_message


class PathfindingService(gevent.Greenlet):
    # pylint: disable=too-many-instance-attributes
    def __init__(  # pylint: disable=too-many-arguments
        self,
        web3: Web3,
        contracts: Dict[str, Contract],
        private_key: PrivateKey,
        db_filename: str,
        sync_start_block: BlockNumber,
        required_confirmations: BlockTimeout,
        poll_interval: float,
        matrix_servers: Optional[List[str]] = None,
    ):
        super().__init__()

        self.web3 = web3
        self.registry_address = contracts[CONTRACT_TOKEN_NETWORK_REGISTRY].address
        self.user_deposit_contract = contracts[CONTRACT_USER_DEPOSIT]
        self.service_token_address = self.user_deposit_contract.functions.token().call()
        self.chain_id = ChainID(web3.eth.chainId)
        self.address = private_key_to_address(private_key)
        self.required_confirmations = required_confirmations
        self._poll_interval = poll_interval
        self._is_running = gevent.event.Event()

        log.info("PFS payment address", address=self.address)

        self.database = PFSDatabase(
            filename=db_filename,
            pfs_address=self.address,
            sync_start_block=sync_start_block,
            token_network_registry_address=to_canonical_address(self.registry_address),
            chain_id=self.chain_id,
            user_deposit_contract_address=to_canonical_address(self.user_deposit_contract.address),
            allow_create=True,
        )

        self.blockchain_state = BlockchainState(
            latest_committed_block=self.database.get_latest_committed_block(),
            token_network_registry_address=to_canonical_address(self.registry_address),
            chain_id=self.chain_id,
        )

        self.matrix_listener = MatrixListener(
            private_key=private_key,
            chain_id=self.chain_id,
            device_id=DeviceIDs.PFS,
            message_received_callback=self.handle_message,
            servers=matrix_servers,
        )

        self.token_networks = self._load_token_networks()
        self.updated = gevent.event.Event()  # set whenever blocks are processed
        self.startup_finished = gevent.event.AsyncResult()

        self._init_metrics()

    def _init_metrics(self) -> None:
        def _get_number_of_claimed_ious() -> float:
            return float(self.database.get_nof_claimed_ious())

        def _get_total_amount_of_claimed_ious() -> float:
            return float(sum(iou.amount for iou in self._iter_claimed_ious()))

        metrics.get_metrics_for_label(
            metrics.IOU_CLAIMS, metrics.IouStatus.SUCCESSFUL
        ).set_function(_get_number_of_claimed_ious)
        metrics.get_metrics_for_label(
            metrics.IOU_CLAIMS_TOKEN, metrics.IouStatus.SUCCESSFUL
        ).set_function(_get_total_amount_of_claimed_ious)

    def _iter_claimed_ious(self) -> Iterator[IOU]:
        return self.database.get_ious(claimed=True)

    def _load_token_networks(self) -> Dict[TokenNetworkAddress, TokenNetwork]:
        network_for_address = {n.address: n for n in self.database.get_token_networks()}
        for channel in self.database.get_channels():
            for cv in channel.views:
                network_for_address[cv.token_network_address].add_channel_view(cv)

        return network_for_address

    def _run(self) -> None:  # pylint: disable=method-hidden
        try:
            self.matrix_listener.start()
        except (Timeout, ConnectionError) as exc:
            log.critical("Could not connect to broadcasting system.", exc=exc)
            sys.exit(1)

        self.matrix_listener.link(self.startup_finished)
        try:
            self.matrix_listener.startup_finished.get(timeout=MATRIX_START_TIMEOUT)
        except Timeout:
            raise Exception("MatrixListener did not start in time.")
        self.startup_finished.set()

        log.info(
            "Listening to token network registry",
            registry_address=self.registry_address,
            start_block=self.database.get_latest_committed_block(),
        )
        while not self._is_running.is_set():
            self._process_new_blocks(
                BlockNumber(self.web3.eth.blockNumber - self.required_confirmations)
            )

            # Let tests waiting for this event know that we're done with processing
            self.updated.set()
            self.updated.clear()

            # Sleep, then collect errors from greenlets
            gevent.sleep(self._poll_interval)
            gevent.joinall({self.matrix_listener}, timeout=0, raise_error=True)

    def _process_new_blocks(self, latest_confirmed_block: BlockNumber) -> None:
        start = time.monotonic()

        db_block = self.database.get_latest_committed_block()
        assert db_block == self.blockchain_state.latest_committed_block, (
            f"Unexpected `latest_committed_block` in db: "
            f"was {db_block}, expected {self.blockchain_state.latest_committed_block}. "
            f"Is the db accidentally shared by two PFSes?"
        )

        events = get_blockchain_events_adaptive(
            web3=self.web3,
            blockchain_state=self.blockchain_state,
            token_network_addresses=list(self.token_networks.keys()),
            latest_confirmed_block=latest_confirmed_block,
        )

        if events is None:
            return

        before_process = time.monotonic()
        for event in events:
            self.handle_event(event)
            gevent.idle()  # Allow answering requests in between events

        if events:
            log.info(
                "Processed events",
                getting=round(before_process - start, 2),
                processing=round(time.monotonic() - before_process, 2),
                total_duration=round(time.monotonic() - start, 2),
                event_counts=collections.Counter(e.__class__.__name__ for e in events),
            )

    def stop(self) -> None:
        self.matrix_listener.kill()
        self._is_running.set()
        self.matrix_listener.join()

    def follows_token_network(self, token_network_address: TokenNetworkAddress) -> bool:
        """Checks if a token network is followed by the pathfinding service."""
        return token_network_address in self.token_networks.keys()

    def get_token_network(
        self, token_network_address: TokenNetworkAddress
    ) -> Optional[TokenNetwork]:
        """Returns the `TokenNetwork` for the given address or `None` for unknown networks."""
        return self.token_networks.get(token_network_address)

    def handle_event(self, event: Event) -> None:
        with sentry_sdk.configure_scope() as scope:
            with metrics.collect_event_metrics(event):
                scope.set_extra("event", event)
                if isinstance(event, ReceiveTokenNetworkCreatedEvent):
                    self.handle_token_network_created(event)
                elif isinstance(event, ReceiveChannelOpenedEvent):
                    self.handle_channel_opened(event)
                elif isinstance(event, ReceiveChannelClosedEvent):
                    self.handle_channel_closed(event)
                elif isinstance(event, UpdatedHeadBlockEvent):
                    # TODO: Store blockhash here as well
                    self.blockchain_state.latest_committed_block = event.head_block_number
                    self.database.update_lastest_committed_block(event.head_block_number)
                else:
                    log.debug("Unhandled event", evt=event)

    def handle_token_network_created(self, event: ReceiveTokenNetworkCreatedEvent) -> None:
        network_address = event.token_network_address
        if not self.follows_token_network(network_address):
            log.info("Found new token network", event_=event)

            self.token_networks[network_address] = TokenNetwork(network_address)
            self.database.upsert_token_network(network_address)

    def handle_channel_opened(self, event: ReceiveChannelOpenedEvent) -> None:
        token_network = self.get_token_network(event.token_network_address)
        if token_network is None:
            return

        log.info("Received ChannelOpened event", event_=event)

        channel = token_network.handle_channel_opened_event(
            channel_identifier=event.channel_identifier,
            participant1=event.participant1,
            participant2=event.participant2,
            settle_timeout=event.settle_timeout,
        )
        self.database.upsert_channel(channel)

        # Handle messages for this channel which where received before ChannelOpened
        with self.database.conn:
            for message in self.database.pop_waiting_messages(
                token_network_address=token_network.address, channel_id=event.channel_identifier
            ):
                log.debug("Processing deferred message", message=message)
                self.handle_message(message)

    def handle_channel_closed(self, event: ReceiveChannelClosedEvent) -> None:
        token_network = self.get_token_network(event.token_network_address)
        if token_network is None:
            return

        log.info("Received ChannelClosed event", event_=event)

        channel_deleted = self.database.delete_channel(
            event.token_network_address, event.channel_identifier
        )
        if channel_deleted:
            token_network.handle_channel_closed_event(event.channel_identifier)
        else:
            log.error(
                "Received ChannelClosed event for unknown channel",
                token_network_address=event.token_network_address,
                channel_identifier=event.channel_identifier,
            )
            metrics.get_metrics_for_label(metrics.ERRORS_LOGGED, metrics.ErrorCategory.STATE).inc()

    def handle_message(self, message: Message) -> None:
        with sentry_sdk.configure_scope() as scope:
            scope.set_extra("message", message)
            try:
                with metrics.collect_message_metrics(message):
                    if isinstance(message, PFSCapacityUpdate):
                        changed_channel: Optional[Channel] = self.on_capacity_update(message)
                    elif isinstance(message, PFSFeeUpdate):
                        changed_channel = self.on_fee_update(message)
                    else:
                        log.debug("Ignoring message", unknown_message=message)
                        return

                    if changed_channel:
                        self.database.upsert_channel(changed_channel)

            except DeferMessage as ex:
                self.defer_message_until_channel_is_open(ex.deferred_message)
            except InvalidGlobalMessage as ex:
                log.info(str(ex), **asdict(message))

    def defer_message_until_channel_is_open(self, message: DeferableMessage) -> None:
        log.debug(
            "Received message for unknown channel, defer until ChannelOpened is confirmed",
            channel_id=message.canonical_identifier.channel_identifier,
            message=message,
        )
        self.database.insert_waiting_message(message)

    def _validate_pfs_fee_update(self, message: PFSFeeUpdate) -> TokenNetwork:
        # check if chain_id matches
        if message.canonical_identifier.chain_identifier != self.chain_id:
            raise InvalidFeeUpdate("Received Fee Update with unknown chain identifier")

        # check if token network exists
        token_network = self.get_token_network(message.canonical_identifier.token_network_address)
        if token_network is None:
            raise InvalidFeeUpdate("Received Fee Update with unknown token network")

        # check signature of Capacity Update
        if message.sender != message.updating_participant:
            raise InvalidFeeUpdate("Fee Update not signed correctly")

        # check if channel exists
        channel_identifier = message.canonical_identifier.channel_identifier
        if channel_identifier not in token_network.channel_id_to_addresses:
            raise DeferMessage(message)

        # check if participants fit to channel id
        participants = token_network.channel_id_to_addresses[channel_identifier]
        if message.updating_participant not in participants:
            raise InvalidFeeUpdate("Sender of Fee Update does not match the internal channel")

        # check that timestamp has no timezone
        if message.timestamp.tzinfo is not None:
            raise InvalidFeeUpdate("Timestamp of Fee Update should not contain timezone")

        return token_network

    def on_fee_update(self, message: PFSFeeUpdate) -> Optional[Channel]:
        token_network = self._validate_pfs_fee_update(message)
        log.debug("Received Fee Update", message=message)

        return token_network.handle_channel_fee_update(message)

    def _validate_pfs_capacity_update(self, message: PFSCapacityUpdate) -> TokenNetwork:
        # check if chain_id matches
        if message.canonical_identifier.chain_identifier != self.chain_id:
            raise InvalidCapacityUpdate("Received Capacity Update with unknown chain identifier")

        # check if token network exists
        token_network = self.get_token_network(message.canonical_identifier.token_network_address)
        if token_network is None:
            raise InvalidCapacityUpdate("Received Capacity Update with unknown token network")

        # check values < max int 256
        if message.updating_capacity > UINT256_MAX:
            raise InvalidCapacityUpdate(
                "Received Capacity Update with impossible updating_capacity"
            )
        if message.other_capacity > UINT256_MAX:
            raise InvalidCapacityUpdate("Received Capacity Update with impossible other_capacity")

        # check signature of Capacity Update
        if message.sender != message.updating_participant:
            raise InvalidCapacityUpdate("Capacity Update not signed correctly")

        # check if channel exists
        channel_identifier = message.canonical_identifier.channel_identifier
        if channel_identifier not in token_network.channel_id_to_addresses:
            raise DeferMessage(message)

        # check if participants fit to channel id
        participants = token_network.channel_id_to_addresses[channel_identifier]
        if message.updating_participant not in participants:
            raise InvalidCapacityUpdate(
                "Sender of Capacity Update does not match the internal channel"
            )
        if message.other_participant not in participants:
            raise InvalidCapacityUpdate(
                "Other Participant of Capacity Update does not match the internal channel"
            )

        return token_network

    def on_capacity_update(self, message: PFSCapacityUpdate) -> Channel:
        token_network = self._validate_pfs_capacity_update(message)
        log.debug("Received Capacity Update", message=message)
        self.database.upsert_capacity_update(message)

        updating_capacity_partner, other_capacity_partner = self.database.get_capacity_updates(
            updating_participant=message.other_participant,
            token_network_address=TokenNetworkAddress(
                message.canonical_identifier.token_network_address
            ),
            channel_id=message.canonical_identifier.channel_identifier,
        )
        return token_network.handle_channel_balance_update_message(
            message=message,
            updating_capacity_partner=updating_capacity_partner,
            other_capacity_partner=other_capacity_partner,
        )
