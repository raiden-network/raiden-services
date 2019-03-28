import sys
import traceback
from typing import Dict, List, Optional

import gevent
import structlog
from eth_utils import is_checksum_address, to_checksum_address
from web3 import Web3

from pathfinding_service.database import PFSDatabase
from pathfinding_service.exceptions import InvalidCapacityUpdate
from pathfinding_service.model import TokenNetwork
from pathfinding_service.utils.blockchain_listener import (
    BlockchainListener,
    create_channel_event_topics,
    create_registry_event_topics,
)
from raiden.constants import PATH_FINDING_BROADCASTING_ROOM, UINT256_MAX
from raiden.messages import SignedMessage, UpdatePFS
from raiden_contracts.constants import (
    CONTRACT_TOKEN_NETWORK,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
    ChannelEvent,
)
from raiden_contracts.contract_manager import ContractManager
from raiden_libs.gevent_error_handler import register_error_handler
from raiden_libs.matrix import MatrixListener
from raiden_libs.types import Address
from raiden_libs.utils import private_key_to_address

log = structlog.get_logger(__name__)


def error_handler(context, exc_info):
    log.critical(
        'Unhandled exception. Terminating the program...'
        'Please report this issue at '
        'https://github.com/raiden-network/raiden-services/issues',
    )
    traceback.print_exception(
        etype=exc_info[0],
        value=exc_info[1],
        tb=exc_info[2],
    )
    sys.exit()


class PathfindingService(gevent.Greenlet):
    def __init__(
            self,
            web3: Web3,
            contract_manager: ContractManager,
            registry_address: Address,
            private_key: str,
            db_filename: str,
            user_deposit_contract_address: Address,
            sync_start_block: int = 0,
            required_confirmations: int = 8,
            poll_interval: int = 10,
            service_fee: int = 0,
    ):
        """ Creates a new pathfinding service

        Args:
            contract_manager: A contract manager
            token_network_listener: A blockchain listener object
            token_network_registry_listener: A blockchain listener object for the network registry
            chain_id: The id of the chain the PFS runs on
        """
        super().__init__()

        self.web3 = web3
        self.contract_manager = contract_manager
        self.registry_address = registry_address
        self.sync_start_block = sync_start_block
        self.required_confirmations = required_confirmations
        self.poll_interval = poll_interval
        self.chain_id = int(web3.net.version)
        self.private_key = private_key
        self.address = private_key_to_address(private_key)
        self.service_fee = service_fee

        self.is_running = gevent.event.Event()
        self.token_networks: Dict[Address, TokenNetwork] = {}
        self.token_network_listeners: List[BlockchainListener] = []
        self.database = PFSDatabase(
            filename=db_filename,
            pfs_address=self.address,
        )
        self.user_deposit_contract = web3.eth.contract(
            abi=self.contract_manager.get_contract_abi(
                CONTRACT_USER_DEPOSIT,
            ),
            address=user_deposit_contract_address,
        )

        log.info(
            'Starting TokenNetworkRegistry Listener',
            required_confirmations=self.required_confirmations,
        )
        self.token_network_registry_listener = BlockchainListener(
            web3=web3,
            contract_manager=self.contract_manager,
            contract_name=CONTRACT_TOKEN_NETWORK_REGISTRY,
            contract_address=self.registry_address,
            required_confirmations=self.required_confirmations,
            poll_interval=self.poll_interval,
            sync_start_block=self.sync_start_block,
        )
        log.info(
            'Listening to token network registry',
            registry_address=registry_address,
            start_block=sync_start_block,
        )
        self._setup_token_networks()

        try:
            self.matrix_listener = MatrixListener(
                private_key=private_key,
                chain_id=self.chain_id,
                callback=self.handle_message,
                service_room_suffix=PATH_FINDING_BROADCASTING_ROOM,
            )
        except ConnectionError as e:
            log.critical(
                'Could not connect to broadcasting system.',
                exc=e,
            )
            sys.exit(1)

    def _setup_token_networks(self):
        self.token_network_registry_listener.add_confirmed_listener(
            create_registry_event_topics(self.contract_manager),
            self.handle_token_network_created,
        )

    def _run(self):
        register_error_handler(error_handler)
        self.matrix_listener.start()
        self.token_network_registry_listener.start()
        self.is_running.wait()

    def stop(self):
        self.token_network_registry_listener.stop()
        for task in self.token_network_listeners:
            task.stop()
        self.matrix_listener.stop()
        self.is_running.set()
        self.matrix_listener.join()

    def follows_token_network(self, token_network_address: Address) -> bool:
        """ Checks if a token network is followed by the pathfinding service. """
        assert is_checksum_address(token_network_address)

        return token_network_address in self.token_networks.keys()

    def _get_token_network(self, token_network_address: Address) -> Optional[TokenNetwork]:
        """ Returns the `TokenNetwork` for the given address or `None` for unknown networks. """

        assert is_checksum_address(token_network_address)
        if not self.follows_token_network(token_network_address):
            return None
        else:
            return self.token_networks[token_network_address]

    def handle_channel_event(self, event: Dict):
        event_name = event['event']

        if event_name == ChannelEvent.OPENED:
            self.handle_channel_opened(event)
        elif event_name == ChannelEvent.DEPOSIT:
            self.handle_channel_new_deposit(event)
        elif event_name == ChannelEvent.CLOSED:
            self.handle_channel_closed(event)
        else:
            log.debug('Unhandled event', evt=event)

    def handle_channel_opened(self, event: Dict):
        token_network = self._get_token_network(event['address'])

        if token_network is None:
            return

        channel_identifier = event['args']['channel_identifier']
        participant1 = event['args']['participant1']
        participant2 = event['args']['participant2']
        settle_timeout = event['args']['settle_timeout']

        log.info(
            'Received ChannelOpened event',
            token_network_address=token_network.address,
            channel_identifier=channel_identifier,
            participant1=participant1,
            participant2=participant2,
            settle_timeout=settle_timeout,
        )

        token_network.handle_channel_opened_event(
            channel_identifier,
            participant1,
            participant2,
            settle_timeout,
        )

    def handle_channel_new_deposit(self, event: Dict):
        token_network = self._get_token_network(event['address'])

        if token_network is None:
            return

        channel_identifier = event['args']['channel_identifier']
        participant_address = event['args']['participant']
        total_deposit = event['args']['total_deposit']

        log.info(
            'Received ChannelNewDeposit event',
            token_network_address=token_network.address,
            channel_identifier=channel_identifier,
            participant=participant_address,
            total_deposit=total_deposit,
        )

        token_network.handle_channel_new_deposit_event(
            channel_identifier,
            participant_address,
            total_deposit,
        )

    def handle_channel_closed(self, event: Dict):
        token_network = self._get_token_network(event['address'])

        if token_network is None:
            return

        channel_identifier = event['args']['channel_identifier']

        log.info(
            'Received ChannelClosed event',
            token_network_address=token_network.address,
            channel_identifier=channel_identifier,
        )

        token_network.handle_channel_closed_event(channel_identifier)

    def handle_token_network_created(self, event):
        token_network_address = event['args']['token_network_address']
        token_address = event['args']['token_address']
        event_block_number = event['blockNumber']

        assert is_checksum_address(token_network_address)
        assert is_checksum_address(token_address)

        if not self.follows_token_network(token_network_address):
            log.info(
                'Found new token network',
                token_address=token_address,
                token_network_address=token_network_address,
            )
            self.create_token_network_for_address(
                token_network_address,
                token_address,
                event_block_number,
            )

    def create_token_network_for_address(
        self,
        token_network_address: Address,
        token_address: Address,
        block_number: int = 0,
    ):
        token_network = TokenNetwork(token_network_address, token_address)
        self.token_networks[token_network_address] = token_network

        log.debug('Creating token network model', token_network_address=token_network_address)
        token_network_listener = BlockchainListener(
            web3=self.web3,
            contract_manager=self.contract_manager,
            contract_address=token_network_address,
            contract_name=CONTRACT_TOKEN_NETWORK,
            required_confirmations=self.required_confirmations,
            poll_interval=self.poll_interval,
            sync_start_block=block_number,
        )

        # subscribe to event notifications from blockchain listener
        token_network_listener.add_confirmed_listener(
            create_channel_event_topics(),
            self.handle_channel_event,
        )
        token_network_listener.start()
        self.token_network_listeners.append(token_network_listener)

    def handle_message(self, message: SignedMessage):
        if isinstance(message, UpdatePFS):
            try:
                self.on_pfs_update(message)
            except InvalidCapacityUpdate as x:
                log.info(
                    str(x),
                    chain_id=message.canonical_identifier.chain_identifier,
                    token_network_address=message.canonical_identifier.token_network_address,
                    channel_identifier=message.canonical_identifier.channel_identifier,
                    updating_capacity=message.updating_capacity,
                    other_capacity=message.updating_capacity,
                )
        else:
            log.info('Ignoring unknown message type')

    def on_pfs_update(self, message: UpdatePFS):
        token_network_address = to_checksum_address(
            message.canonical_identifier.token_network_address,
        )
        log.info(
            'Received Capacity Update',
            token_network_address=token_network_address,
            channel_identifier=message.canonical_identifier.channel_identifier,
        )

        updating_participant = to_checksum_address(message.updating_participant)
        other_participant = to_checksum_address(message.other_participant)

        # check if chain_id matches
        if message.canonical_identifier.chain_identifier != self.chain_id:
            raise InvalidCapacityUpdate('Received Capacity Update with unknown chain identifier')

        # check if token network exists
        token_network = self._get_token_network(token_network_address)
        if token_network is None:
            raise InvalidCapacityUpdate('Received Capacity Update with unknown token network')

        # check if channel exists
        channel_identifier = message.canonical_identifier.channel_identifier
        if channel_identifier not in token_network.channel_id_to_addresses:
            raise InvalidCapacityUpdate(
                'Received Capacity Update with unknown channel identifier in token network',
            )

        # TODO: check signature of message

        # check values < max int 256
        if message.updating_capacity > UINT256_MAX:
            raise InvalidCapacityUpdate(
                'Received Capacity Update with impossible updating_capacity',
            )
        if message.other_capacity > UINT256_MAX:
            raise InvalidCapacityUpdate(
                'Received Capacity Update with impossible other_capacity',
            )

        # check if participants fit to channel id
        participants = token_network.channel_id_to_addresses[channel_identifier]
        if updating_participant not in participants:
            raise InvalidCapacityUpdate(
                'Sender of Capacity Update does not match the internal channel',
            )
        if other_participant not in participants:
            raise InvalidCapacityUpdate(
                'Other Participant of Capacity Update does not match the internal channel',
            )

        # check if nonce is higher than current nonce
        view_to_partner, view_from_partner = token_network.get_channel_views_for_partner(
            channel_identifier=channel_identifier,
            updating_participant=updating_participant,
            other_participant=other_participant,
        )

        valid_nonces = (
            message.updating_nonce <= view_to_partner.update_nonce and
            message.other_nonce <= view_from_partner.update_nonce
        )
        if valid_nonces:
            raise InvalidCapacityUpdate('Capacity Update already received')

        token_network.handle_channel_balance_update_message(
            channel_identifier=message.canonical_identifier.channel_identifier,
            updating_participant=updating_participant,
            other_participant=other_participant,
            updating_nonce=message.updating_nonce,
            other_nonce=message.other_nonce,
            updating_capacity=message.updating_capacity,
            other_capacity=message.other_capacity,
            reveal_timeout=message.reveal_timeout,
        )
