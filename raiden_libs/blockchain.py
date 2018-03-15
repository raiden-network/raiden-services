# -*- coding: utf-8 -*-
import functools
import logging
import sys
import requests
from typing import Callable, Dict, Union, List

from web3 import Web3
from web3.contract import get_event_data
from web3.utils.filters import construct_event_filter_params, LogFilter
import gevent

from raiden_libs.contracts import ContractManager


log = logging.getLogger(__name__)


def create_event_filter(
        web3: Web3,
        event_name: str,
        event_abi: Dict,
        filter_params: Dict = {}
) -> LogFilter:
    """Create filter object that tracks events emitted.

    Args:
        web3: A web3 client
        event_name: The name of the event to track
        event_abi: The ABI of the event to track
        filter_params: Other parameters to limit the events

    Returns:
        A LogFilter instance"""
    filter_meta_params = dict(filter_params)

    data_filter_set, event_filter_params = construct_event_filter_params(
        event_abi,
        **filter_meta_params
    )

    log_data_extract_fn = functools.partial(get_event_data, event_abi)

    log_filter = web3.eth.filter(event_filter_params)

    log_filter.set_data_filters(data_filter_set)
    log_filter.log_entry_formatter = log_data_extract_fn
    log_filter.filter_params = event_filter_params

    return log_filter


def get_events(
        w3: Web3,
        contract_manager: ContractManager,
        contract_name: str,
        event_name: str,
        from_block: Union[int, str] = 0,
        to_block: Union[int, str] = 'latest',
) -> List:
    """Returns events emmitted by a contract for a given event name, within a certain range.

    Args:
        w3: A Web3 instance
        contract_manager: A contract manager
        contract_name: The name of the contract
        event_name: The name of the event
        from_block: The block to start search events
        to_block: The block to stop searching for events

    Returns:
        All matching events"""
    filter = create_event_filter(
        web3=w3,
        event_name=event_name,
        event_abi=contract_manager.get_event_abi(contract_name, event_name),
        filter_params={
            'fromBlock': from_block,
            'toBlock': to_block,
        }
    )
    events = filter.get_all_entries()

    w3.eth.uninstallFilter(filter.filter_id)
    return events


class BlockchainListener(gevent.Greenlet):
    """ A class listening for events on a given contract. """

    def __init__(
            self,
            web3: Web3,
            contract_manager: ContractManager,
            contract_name: str,
            required_confirmations: int = 4,
            sync_chunk_size: int = 100_000,
            poll_interval: int = 2,
            sync_start_block: int = 0
    ):
        """Creates a new BlockchainListener

        Args:
            web3: A Web3 instance
            contract_manager: A contract manager
            contract_name: The name of the contract
            required_confirmations: The number of confirmations required to call a block confirmed
            sync_chunk_size: The size of the chunks used during syncing
            poll_interval: The interval used between polls
            sync_start_block: The block number syncing is started at"""
        self.contract_manager = contract_manager
        self.contract_name = contract_name

        self.required_confirmations = required_confirmations
        self.web3 = web3

        self.confirmed_callbacks: Dict[str, Callable] = {}
        self.unconfirmed_callbacks: Dict[str, Callable] = {}

        self.wait_sync_event = gevent.event.Event()
        self.is_connected = gevent.event.Event()
        self.sync_chunk_size = sync_chunk_size
        self.running = False
        self.poll_interval = poll_interval

        self.unconfirmed_head_number = sync_start_block
        self.confirmed_head_number = sync_start_block
        self.unconfirmed_head_hash = None
        self.confirmed_head_hash = None

    def add_confirmed_listener(self, event_name: str, callback: Callable):
        """ Add a callback to listen for confirmed events. """
        self.confirmed_callbacks[event_name] = callback

    def add_unconfirmed_listener(self, event_name: str, callback: Callable):
        """ Add a callback to listen for unconfirmed events. """
        self.unconfirmed_callbacks[event_name] = callback

    def _run(self):
        self.running = True
        log.info('Starting blockchain polling (interval %ss)', self.poll_interval)
        while self.running:
            try:
                self._update()
                self.is_connected.set()
                if self.wait_sync_event.is_set():
                    gevent.sleep(self.poll_interval)
            except requests.exceptions.ConnectionError as e:
                endpoint = self.web3.currentProvider.endpoint_uri
                log.warning(
                    'Ethereum node (%s) refused connection. Retrying in %d seconds.' %
                    (endpoint, self.poll_interval)
                )
                gevent.sleep(self.poll_interval)
                self.is_connected.clear()
            log.info('Stopped blockchain polling')

    def stop(self):
        """ Stops the BlockchainListener. """
        self.running = False

    def wait_sync(self):
        """Blocks until event polling is up-to-date with a most recent block of the blockchain. """
        self.wait_sync_event.wait()

    def _update(self):
        current_block = self.web3.eth.blockNumber

        # reset unconfirmed channels in case of reorg
        if self.wait_sync_event.is_set():  # but not on first sync
            if current_block < self.unconfirmed_head_number:
                log.info('Chain reorganization detected. '
                         'Resyncing unconfirmed events (unconfirmed_head=%d) [@%d]' %
                         (self.unconfirmed_head_number, self.web3.eth.blockNumber))
                self.cm.reset_unconfirmed()
            try:
                # raises if hash doesn't exist (i.e. block has been replaced)
                self.web3.eth.getBlock(self.unconfirmed_head_hash)
            except ValueError:
                log.info('Chain reorganization detected. '
                         'Resyncing unconfirmed events (unconfirmed_head=%d) [@%d]. '
                         '(getBlock() raised ValueError)' %
                         (self.unconfirmed_head_number, current_block))
                self.unconfirmed_head_number = self.confirmed_head_number
                self.unconfirmed_head_hash = self.confirmed_head_hash

            # in case of reorg longer than confirmation number fail
            try:
                self.web3.eth.getBlock(self.confirmed_head_hash)
            except ValueError:
                log.critical('Events considered confirmed have been reorganized')
                assert False  # unreachable as long as confirmation level is set high enough

        new_unconfirmed_head_number = self.unconfirmed_head_number + self.sync_chunk_size
        new_unconfirmed_head_number = min(new_unconfirmed_head_number, current_block)
        new_confirmed_head_number = max(
            new_unconfirmed_head_number - self.required_confirmations,
            0
        )

        # return if blocks have already been processed
        if (self.confirmed_head_number >= new_confirmed_head_number and
                self.unconfirmed_head_number >= new_unconfirmed_head_number):
            return

        # filter for events after block_number
        filters_confirmed = {
            'from_block': self.confirmed_head_number + 1,
            'to_block': new_confirmed_head_number,
        }
        filters_unconfirmed = {
            'from_block': self.unconfirmed_head_number + 1,
            'to_block': new_unconfirmed_head_number,
        }
        log.debug(
            'Filtering for events u:%s-%s c:%s-%s @%d',
            filters_unconfirmed['from_block'],
            filters_unconfirmed['to_block'],
            filters_confirmed['from_block'],
            filters_confirmed['to_block'],
            current_block
        )

        # filter confirmed events
        for event_name, callback in self.confirmed_callbacks.items():
            events = get_events(
                self.web3,
                self.contract_manager,
                self.contract_name,
                event_name,
                **filters_confirmed
            )
            for event in events:
                log.debug('Received confirmed %s event', event_name)
                callback(event)

        # filter unconfirmed events
        for event_name, callback in self.unconfirmed_callbacks.items():
            events = get_events(
                self.web3,
                self.contract_manager,
                self.contract_name,
                event_name,
                **filters_unconfirmed
            )
            for event in events:
                log.debug('Received unconfirmed %s event', event_name)
                callback(event)

        # update head hash and number
        try:
            new_unconfirmed_head_hash = self.web3.eth.getBlock(new_unconfirmed_head_number).hash
            new_confirmed_head_hash = self.web3.eth.getBlock(new_confirmed_head_number).hash
        except AttributeError:
            log.critical("RPC endpoint didn't return proper info for an existing block "
                         "(%d,%d)" % (new_unconfirmed_head_number, new_confirmed_head_number))
            log.critical("It is possible that the blockchain isn't fully synced. "
                         "This often happens when Parity is run with --fast or --warp sync.")
            log.critical("Cannot continue - check status of the ethereum node.")
            sys.exit(1)

        self.unconfirmed_head_number = new_unconfirmed_head_number
        self.unconfirmed_head_hash = new_unconfirmed_head_hash
        self.confirmed_head_number = new_confirmed_head_number
        self.confirmed_head_hash = new_confirmed_head_hash

        if not self.wait_sync_event.is_set() and new_unconfirmed_head_number == current_block:
            self.wait_sync_event.set()
