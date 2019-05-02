import sys
from dataclasses import asdict
from typing import Dict, Optional

import gevent
import structlog
from eth_utils import is_same_address, to_checksum_address
from web3 import Web3
from web3.contract import Contract

from monitoring_service.constants import MAX_FILTER_INTERVAL
from pathfinding_service.database import PFSDatabase
from pathfinding_service.exceptions import InvalidCapacityUpdate
from pathfinding_service.model import TokenNetwork
from raiden.constants import PATH_FINDING_BROADCASTING_ROOM, UINT256_MAX
from raiden.messages import SignedMessage, UpdatePFS
from raiden.utils.typing import BlockNumber, ChainID, TokenNetworkAddress
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
from raiden_libs.types import Address
from raiden_libs.utils import private_key_to_address

log = structlog.get_logger(__name__)


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

        self.database = PFSDatabase(
            filename=db_filename,
            pfs_address=self.address,
            sync_start_block=sync_start_block,
            token_network_registry_address=self.registry_address,
            chain_id=self.chain_id,
            user_deposit_contract_address=self.user_deposit_contract.address,
            allow_create=True,
        )
        self.token_networks = self._load_token_networks()

        try:
            self.matrix_listener = MatrixListener(
                private_key=private_key,
                chain_id=self.chain_id,
                callback=self.handle_message,
                service_room_suffix=PATH_FINDING_BROADCASTING_ROOM,
            )
        except ConnectionError as exc:
            log.critical("Could not connect to broadcasting system.", exc=exc)
            sys.exit(1)

    def _load_token_networks(self) -> Dict[TokenNetworkAddress, TokenNetwork]:
        network_for_address = {n.address: n for n in self.database.get_token_networks()}
        channel_views = self.database.get_channel_views()
        for cv in channel_views:
            network_for_address[cv.token_network_address].add_channel_view(cv)
        return network_for_address

    def _run(self) -> None:  # pylint: disable=method-hidden
        register_error_handler()
        self.matrix_listener.start()

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
        _, events = get_blockchain_events(
            web3=self.web3,
            contract_manager=CONTRACT_MANAGER,
            chain_state=BlockchainState(
                latest_known_block=self.database.get_latest_known_block(),
                token_network_addresses=list(self.token_networks.keys()),
                token_network_registry_address=self.registry_address,
                monitor_contract_address=Address(""),  # FIXME
                chain_id=self.chain_id,
            ),
            to_block=last_block,
            query_ms=False,
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
            log.info("Found new token network", **asdict(event))

            self.token_networks[network_address] = TokenNetwork(network_address)
            self.database.upsert_token_network(network_address)

    def handle_channel_opened(self, event: ReceiveChannelOpenedEvent) -> None:
        token_network = self.get_token_network(event.token_network_address)
        if token_network is None:
            return

        log.info("Received ChannelOpened event", **asdict(event))

        channel_views = token_network.handle_channel_opened_event(
            channel_identifier=event.channel_identifier,
            participant1=event.participant1,
            participant2=event.participant2,
            settle_timeout=event.settle_timeout,
        )
        for cv in channel_views:
            self.database.upsert_channel_view(cv)

    def handle_channel_new_deposit(self, event: ReceiveChannelNewDepositEvent) -> None:
        token_network = self.get_token_network(event.token_network_address)
        if token_network is None:
            return

        log.info("Received ChannelNewDeposit event", **asdict(event))

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

        log.info("Received ChannelClosed event", **asdict(event))

        token_network.handle_channel_closed_event(channel_identifier=event.channel_identifier)
        self.database.delete_channel_views(event.channel_identifier)

    def handle_message(self, message: SignedMessage) -> None:
        if isinstance(message, UpdatePFS):
            try:
                self.on_pfs_update(message)
            except InvalidCapacityUpdate as x:
                log.info(str(x), **message.to_dict())
        else:
            log.info("Ignoring unknown message type")

    def _validate_pfs_update(self, message: UpdatePFS) -> TokenNetwork:
        token_network_address = TokenNetworkAddress(
            message.canonical_identifier.token_network_address
        )

        updating_participant = to_checksum_address(message.updating_participant)
        other_participant = to_checksum_address(message.other_participant)

        # check if chain_id matches
        if message.canonical_identifier.chain_identifier != self.chain_id:
            raise InvalidCapacityUpdate("Received Capacity Update with unknown chain identifier")

        # check if token network exists
        token_network = self.get_token_network(token_network_address)
        if token_network is None:
            raise InvalidCapacityUpdate("Received Capacity Update with unknown token network")

        # check if channel exists
        channel_identifier = message.canonical_identifier.channel_identifier
        if channel_identifier not in token_network.channel_id_to_addresses:
            raise InvalidCapacityUpdate(
                "Received Capacity Update with unknown channel identifier in token network"
            )

        # check values < max int 256
        if message.updating_capacity > UINT256_MAX:
            raise InvalidCapacityUpdate(
                "Received Capacity Update with impossible updating_capacity"
            )
        if message.other_capacity > UINT256_MAX:
            raise InvalidCapacityUpdate("Received Capacity Update with impossible other_capacity")

        # check if participants fit to channel id
        participants = token_network.channel_id_to_addresses[channel_identifier]
        if updating_participant not in participants:
            raise InvalidCapacityUpdate(
                "Sender of Capacity Update does not match the internal channel"
            )
        if other_participant not in participants:
            raise InvalidCapacityUpdate(
                "Other Participant of Capacity Update does not match the internal channel"
            )

        # check signature of Capacity Update
        signer = to_checksum_address(message.sender)  # recover address from signature
        if not is_same_address(signer, updating_participant):
            raise InvalidCapacityUpdate("Capacity Update not signed correctly")

        # check if nonce is higher than current nonce
        view_to_partner, view_from_partner = token_network.get_channel_views_for_partner(
            channel_identifier=channel_identifier,
            updating_participant=updating_participant,
            other_participant=other_participant,
        )
        is_nonce_pair_known = (
            message.updating_nonce <= view_to_partner.update_nonce
            and message.other_nonce <= view_from_partner.update_nonce
        )
        if is_nonce_pair_known:
            raise InvalidCapacityUpdate("Capacity Update already received")

        return token_network

    def on_pfs_update(self, message: UpdatePFS) -> None:
        token_network = self._validate_pfs_update(message)
        log.info("Received Capacity Update", **message.to_dict())
        token_network.handle_channel_balance_update_message(message)
