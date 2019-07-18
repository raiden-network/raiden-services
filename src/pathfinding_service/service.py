import sys
from dataclasses import asdict
from typing import Dict, List, Optional

import gevent
import structlog
from web3 import Web3
from web3.contract import Contract

from monitoring_service.constants import MAX_FILTER_INTERVAL
from pathfinding_service.database import PFSDatabase
from pathfinding_service.exceptions import (
    InvalidCapacityUpdate,
    InvalidGlobalMessage,
    InvalidPFSFeeUpdate,
)
from pathfinding_service.model import TokenNetwork
from pathfinding_service.model.channel_view import ChannelView
from pathfinding_service.typing import DeferableMessage
from raiden.constants import PATH_FINDING_BROADCASTING_ROOM, UINT256_MAX
from raiden.messages.abstract import Message
from raiden.messages.path_finding_service import PFSCapacityUpdate, PFSFeeUpdate
from raiden.network.transport.matrix import AddressReachability
from raiden.utils.typing import Address, BlockNumber, ChainID, TokenNetworkAddress
from raiden_contracts.constants import CONTRACT_TOKEN_NETWORK_REGISTRY, CONTRACT_USER_DEPOSIT
from raiden_libs.blockchain import get_blockchain_events
from raiden_libs.contract_info import CONTRACT_MANAGER
from raiden_libs.events import (
    Event,
    ReceiveChannelClosedEvent,
    ReceiveChannelNewDepositEvent,
    ReceiveChannelOpenedEvent,
    ReceiveTokenNetworkCreatedEvent,
    UpdatedHeadBlockEvent,
)
from raiden_libs.gevent_error_handler import register_error_handler
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
        private_key: str,
        db_filename: str,
        sync_start_block: BlockNumber = BlockNumber(0),
        required_confirmations: int = 8,
        poll_interval: float = 10,
    ):
        super().__init__()

        self.web3 = web3
        self.registry_address = contracts[CONTRACT_TOKEN_NETWORK_REGISTRY].address
        self.user_deposit_contract = contracts[CONTRACT_USER_DEPOSIT]
        self.chain_id = ChainID(int(web3.net.version))
        self.address = private_key_to_address(private_key)
        self._required_confirmations = required_confirmations
        self._poll_interval = poll_interval
        self._is_running = gevent.event.Event()

        log.info("PFS payment address", address=self.address)

        self.blockchain_state = BlockchainState(
            latest_known_block=BlockNumber(0),
            token_network_registry_address=self.registry_address,
            chain_id=self.chain_id,
        )

        self.database = PFSDatabase(
            filename=db_filename,
            pfs_address=self.address,
            sync_start_block=sync_start_block,
            token_network_registry_address=self.registry_address,
            chain_id=self.chain_id,
            user_deposit_contract_address=self.user_deposit_contract.address,
            allow_create=True,
        )

        self.matrix_listener = MatrixListener(
            private_key=private_key,
            chain_id=self.chain_id,
            service_room_suffix=PATH_FINDING_BROADCASTING_ROOM,
            message_received_callback=self.handle_message,
            address_reachability_changed_callback=self.handle_reachability_change,
        )

        self.address_to_reachability: Dict[Address, AddressReachability] = dict()
        self.token_networks = self._load_token_networks()

    def _load_token_networks(self) -> Dict[TokenNetworkAddress, TokenNetwork]:
        network_for_address = {n.address: n for n in self.database.get_token_networks()}
        channel_views = self.database.get_channel_views()
        for cv in channel_views:
            network_for_address[cv.token_network_address].add_channel_view(cv)

            # Register channel participants for presence tracking
            self.matrix_listener.follow_address_presence(cv.participant1)
            self.matrix_listener.follow_address_presence(cv.participant2)

        return network_for_address

    def _run(self) -> None:  # pylint: disable=method-hidden
        register_error_handler()
        try:
            self.matrix_listener.start()
        except ConnectionError as exc:
            log.critical("Could not connect to broadcasting system.", exc=exc)
            sys.exit(1)

        log.info(
            "Listening to token network registry",
            registry_address=self.registry_address,
            start_block=self.database.get_latest_known_block(),
        )
        while not self._is_running.is_set():
            last_confirmed_block = self.web3.eth.blockNumber - self._required_confirmations

            max_query_interval_end_block = (
                self.database.get_latest_known_block() + MAX_FILTER_INTERVAL
            )
            # Limit the max number of blocks that is processed per iteration
            last_block = min(last_confirmed_block, max_query_interval_end_block)

            self._process_new_blocks(last_block)

            try:
                gevent.sleep(self._poll_interval)
            except KeyboardInterrupt:
                log.info("Shutting down")
                sys.exit(0)

    def _process_new_blocks(self, last_block: BlockNumber) -> None:
        self.blockchain_state.latest_known_block = self.database.get_latest_known_block()
        self.blockchain_state.token_network_addresses = list(self.token_networks.keys())

        _, events = get_blockchain_events(
            web3=self.web3,
            contract_manager=CONTRACT_MANAGER,
            chain_state=self.blockchain_state,
            to_block=last_block,
        )
        for event in events:
            self.handle_event(event)

    def stop(self) -> None:
        self.matrix_listener.stop()
        self._is_running.set()
        self.matrix_listener.join()

    def follows_token_network(self, token_network_address: TokenNetworkAddress) -> bool:
        """ Checks if a token network is followed by the pathfinding service. """
        return token_network_address in self.token_networks.keys()

    def handle_reachability_change(
        self, address: Address, reachability: AddressReachability
    ) -> None:
        self.address_to_reachability[address] = reachability

    def get_token_network(
        self, token_network_address: TokenNetworkAddress
    ) -> Optional[TokenNetwork]:
        """ Returns the `TokenNetwork` for the given address or `None` for unknown networks. """
        return self.token_networks.get(token_network_address)

    def handle_event(self, event: Event) -> None:
        if isinstance(event, ReceiveTokenNetworkCreatedEvent):
            self.handle_token_network_created(event)
        elif isinstance(event, ReceiveChannelOpenedEvent):
            self.handle_channel_opened(event)
        elif isinstance(event, ReceiveChannelNewDepositEvent):
            self.handle_channel_new_deposit(event)
        elif isinstance(event, ReceiveChannelClosedEvent):
            self.handle_channel_closed(event)
        elif isinstance(event, UpdatedHeadBlockEvent):
            self.database.update_lastest_known_block(event.head_block_number)
        else:
            log.debug("Unhandled event", evt=event)

    def handle_token_network_created(self, event: ReceiveTokenNetworkCreatedEvent) -> None:
        network_address = TokenNetworkAddress(event.token_network_address)
        if not self.follows_token_network(network_address):
            log.info("Found new token network", event_=event)

            self.token_networks[network_address] = TokenNetwork(network_address)
            self.database.upsert_token_network(network_address)

    def handle_channel_opened(self, event: ReceiveChannelOpenedEvent) -> None:
        token_network = self.get_token_network(event.token_network_address)
        if token_network is None:
            return

        log.info("Received ChannelOpened event", event_=event)

        self.matrix_listener.follow_address_presence(event.participant1, refresh=True)
        self.matrix_listener.follow_address_presence(event.participant2, refresh=True)

        channel_views = token_network.handle_channel_opened_event(
            channel_identifier=event.channel_identifier,
            participant1=event.participant1,
            participant2=event.participant2,
            settle_timeout=event.settle_timeout,
        )
        for cv in channel_views:
            self.database.upsert_channel_view(cv)

        # Handle messages for this channel which where received before ChannelOpened
        with self.database.conn:
            for message in self.database.pop_waiting_messages(
                token_network_address=token_network.address, channel_id=event.channel_identifier
            ):
                self.handle_message(message)

    def handle_channel_new_deposit(self, event: ReceiveChannelNewDepositEvent) -> None:
        token_network = self.get_token_network(event.token_network_address)
        if token_network is None:
            return

        log.info("Received ChannelNewDeposit event", event_=event)

        channel_view = token_network.handle_channel_new_deposit_event(
            channel_identifier=event.channel_identifier,
            receiver=event.participant_address,
            total_deposit=event.total_deposit,
        )
        if channel_view:
            self.database.upsert_channel_view(channel_view)

    def handle_channel_closed(self, event: ReceiveChannelClosedEvent) -> None:
        token_network = self.get_token_network(event.token_network_address)
        if token_network is None:
            return

        log.info("Received ChannelClosed event", event_=event)

        token_network.handle_channel_closed_event(channel_identifier=event.channel_identifier)
        self.database.delete_channel_views(event.channel_identifier)

    def handle_message(self, message: Message) -> None:
        try:
            if isinstance(message, PFSCapacityUpdate):
                changed_cvs = self.on_capacity_update(message)
            elif isinstance(message, PFSFeeUpdate):
                changed_cvs = self.on_fee_update(message)
            else:
                log.debug("Ignoring message", message=message)

            for cv in changed_cvs:
                self.database.upsert_channel_view(cv)

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

    def on_fee_update(self, message: PFSFeeUpdate) -> List[ChannelView]:
        if message.sender != message.updating_participant:
            raise InvalidPFSFeeUpdate("Invalid sender recovered from signature in PFSFeeUpdate")

        token_network = self.get_token_network(message.canonical_identifier.token_network_address)
        if not token_network:
            return []

        log.debug("Received Fee Update", message=message)

        if (
            message.canonical_identifier.channel_identifier
            not in token_network.channel_id_to_addresses
        ):
            raise DeferMessage(message)

        return token_network.handle_channel_fee_update(message)

    def _validate_pfs_capacity_update(self, message: PFSCapacityUpdate) -> TokenNetwork:
        token_network_address = TokenNetworkAddress(
            message.canonical_identifier.token_network_address
        )

        # check if chain_id matches
        if message.canonical_identifier.chain_identifier != self.chain_id:
            raise InvalidCapacityUpdate("Received Capacity Update with unknown chain identifier")

        # check if token network exists
        token_network = self.get_token_network(token_network_address)
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

    def on_capacity_update(self, message: PFSCapacityUpdate) -> List[ChannelView]:
        token_network = self._validate_pfs_capacity_update(message)
        log.debug("Received Capacity Update", message=message)
        self.database.upsert_capacity_update(message)

        # Follow presence for the channel participants
        self.matrix_listener.follow_address_presence(message.updating_participant, refresh=True)
        self.matrix_listener.follow_address_presence(message.other_participant, refresh=True)

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
