import logging
from typing import Callable, Dict, List, Set

import gevent
from eth_utils import is_checksum_address
from web3 import Web3

from monitoring_service.utils import BlockchainListener, BlockchainMonitor
from monitoring_service.utils.blockchain_listener import (
    create_channel_event_topics,
    create_registry_event_topics,
)
from raiden_contracts.constants import CONTRACT_TOKEN_NETWORK, CONTRACT_TOKEN_NETWORK_REGISTRY
from raiden_contracts.contract_manager import ContractManager
from raiden_libs.types import Address

log = logging.getLogger(__name__)


class TokenNetworkListener(gevent.Greenlet):
    """ Handle callbacks for channel events in all token networks

    Listen for new token networks in the registry and execute callbacks on
    channel events in all discovered token networks. It is assumed that all
    token networks are meant to be handled in the same way.
    """

    def __init__(
        self,
        web3: Web3,
        contract_manager: ContractManager,
        registry_address: Address,
        sync_start_block: int = 0,
        required_confirmations: int = 8,
        poll_interval: int = 10,
    ):
        super().__init__()

        self.web3 = web3
        self.contract_manager = contract_manager
        self.stop_event = gevent.event.Event()
        self.registry_address = registry_address
        self.sync_start_block = sync_start_block
        self.required_confirmations = required_confirmations
        self.poll_interval = poll_interval
        self.token_networks: Set[Address] = set()
        self.token_network_listeners: List[BlockchainListener] = []
        self.confirmed_channel_event_listeners: List[Callable] = []

        log.info('Starting TokenNetworkRegistry Listener (required confirmations: {})...'.format(
            self.required_confirmations,
        ))
        self.token_network_registry_listener = BlockchainListener(
            web3=self.web3,
            contract_manager=self.contract_manager,
            contract_name=CONTRACT_TOKEN_NETWORK_REGISTRY,
            contract_address=self.registry_address,
            required_confirmations=self.required_confirmations,
            poll_interval=self.poll_interval,
            sync_start_block=self.sync_start_block,
        )
        log.info(
            f'Listening to token network registry @ {registry_address} '
            f'from block {sync_start_block}',
        )
        self.token_network_registry_listener.add_confirmed_listener(
            topics=create_registry_event_topics(self.contract_manager),
            callback=self.handle_token_network_created,
        )

    def handle_token_network_created(self, event: Dict):
        token_network_address = event['args']['token_network_address']
        token_address = event['args']['token_address']
        event_block_number = event['blockNumber']

        assert is_checksum_address(token_network_address)
        assert is_checksum_address(token_address)

        if token_network_address not in self.token_networks:
            log.info(f'Found token network for token {token_address} @ {token_network_address}')

            log.info('Creating token network for %s', token_network_address)
            token_network_listener = BlockchainMonitor(
                web3=self.web3,
                contract_manager=self.contract_manager,
                contract_address=token_network_address,
                contract_name=CONTRACT_TOKEN_NETWORK,
                required_confirmations=self.required_confirmations,
                poll_interval=self.poll_interval,
                sync_start_block=event_block_number,
            )
            token_network_listener.add_confirmed_listener(
                topics=create_channel_event_topics(),
                callback=self.handle_confirmed_events,
            )

            token_network_listener.start()
            self.token_networks.add(token_network_address)
            self.token_network_listeners.append(token_network_listener)

    def _run(self):
        self.token_network_registry_listener.start()
        self.stop_event.wait()

    def stop(self):
        self.token_network_registry_listener.stop()
        for task in self.token_network_listeners:
            task.stop()
        self.stop_event.set()

    def handle_confirmed_events(self, event: Dict, tx: Dict):
        for l in self.confirmed_channel_event_listeners:
            l(event, tx)

    def add_confirmed_channel_event_listener(self, callback: Callable):
        """ Trigger callback on confirmed events in all token networks """
        self.confirmed_channel_event_listeners.append(callback)
