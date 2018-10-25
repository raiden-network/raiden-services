import functools
import logging
import sys
import requests
from typing import Callable, Dict, Union, List

from web3 import Web3
from web3.contract import get_event_data
from web3.utils.filters import construct_event_filter_params, LogFilter
from eth_utils import is_checksum_address
import gevent
import gevent.event
from raiden_contracts.contract_manager import ContractManager


log = logging.getLogger(__name__)


def create_event_filter(
        web3: Web3,
        event_name: str,
        event_abi: Dict,
        filter_params: Dict = None,
) -> LogFilter:
    """Create filter object that tracks events emitted.

    Args:
        web3: A web3 client
        event_name: The name of the event to track
        event_abi: The ABI of the event to track
        filter_params: Other parameters to limit the events

    Returns:
        A LogFilter instance
    """
    if filter_params is None:
        filter_params = {}
    filter_meta_params = dict(filter_params)

    data_filter_set, event_filter_params = construct_event_filter_params(
        event_abi,
        **filter_meta_params,
    )

    log_data_extract_fn = functools.partial(get_event_data, event_abi)

    log_filter = web3.eth.filter(event_filter_params)

    log_filter.set_data_filters(data_filter_set)
    log_filter.log_entry_formatter = log_data_extract_fn
    log_filter.filter_params = event_filter_params

    return log_filter


def get_events(
        web3: Web3,
        contract_manager: ContractManager,
        contract_name: str,
        event_name: str,
        contract_address: str = None,
        from_block: Union[int, str] = 0,
        to_block: Union[int, str] = 'latest',
) -> List:
    """Returns events emmitted by a contract for a given event name, within a certain range.

    Args:
        web3: A Web3 instance
        contract_manager: A contract manager
        contract_name: The name of the contract
        event_name: The name of the event
        contract_address: The address of the contract to be filtered, can be `None`
        from_block: The block to start search events
        to_block: The block to stop searching for events

    Returns:
        All matching events
    """
    filter_params = {
        'fromBlock': from_block,
        'toBlock': to_block,
    }
    if contract_address is not None:
        assert is_checksum_address(contract_address)
        filter_params['contract_address'] = contract_address

    filter = create_event_filter(
        web3=web3,
        event_name=event_name,
        event_abi=contract_manager.get_event_abi(contract_name, event_name),
        filter_params=filter_params,
    )
    events = filter.get_all_entries()

    web3.eth.uninstallFilter(filter.filter_id)
    return events


class BlockchainListener(gevent.Greenlet):
    """ A class listening for events on a given contract. """

    def __init__(
            self,
            web3: Web3,
            contract_manager: ContractManager,
            contract_name: str,
            *,  # require all following arguments to be keyword arguments
            contract_address: str = None,
            required_confirmations: int = 4,
            sync_chunk_size: int = 100_000,
            poll_interval: int = 2,
            sync_start_block: int = 0,
    ) -> None:
        """Creates a new BlockchainListener

        Args:
            web3: A Web3 instance
            contract_manager: A contract manager
            contract_name: The name of the contract
            required_confirmations: The number of confirmations required to call a block confirmed
            sync_chunk_size: The size of the chunks used during syncing
            poll_interval: The interval used between polls
            sync_start_block: The block number syncing is started at
        """
        super().__init__()

        self.contract_manager = contract_manager
        self.contract_name = contract_name
        self.contract_address = contract_address

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
            except requests.exceptions.ConnectionError:
                endpoint = self.web3.currentProvider.endpoint_uri
                log.warning(
                    'Ethereum node (%s) refused connection. Retrying in %d seconds.' %
                    (endpoint, self.poll_interval),
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
        self.reset_unconfirmed_on_reorg(current_block)

        new_unconfirmed_head_number = self.unconfirmed_head_number + self.sync_chunk_size
        new_unconfirmed_head_number = min(new_unconfirmed_head_number, current_block)
        new_confirmed_head_number = max(
            new_unconfirmed_head_number - self.required_confirmations,
            self.confirmed_head_number,
        )

        # return if blocks have already been processed
        if (self.confirmed_head_number >= new_confirmed_head_number and
                self.unconfirmed_head_number >= new_unconfirmed_head_number):
            return

        if self.confirmed_head_number < new_confirmed_head_number:
            # create filters depending on current head number
            filters_confirmed = self.get_filter_params(
                self.confirmed_head_number,
                new_confirmed_head_number,
            )
            log.debug(
                'Filtering for confirmed events: %s-%s @%d',
                filters_confirmed['from_block'],
                filters_confirmed['to_block'],
                current_block,
            )
            # filter the events and run callbacks
            self.filter_events(filters_confirmed, self.confirmed_callbacks)

        if self.unconfirmed_head_number < new_unconfirmed_head_number:
            # create filters depending on current head number
            filters_unconfirmed = self.get_filter_params(
                self.unconfirmed_head_number,
                new_unconfirmed_head_number,
            )
            log.debug(
                'Filtering for unconfirmed events: %s-%s @%d',
                filters_unconfirmed['from_block'],
                filters_unconfirmed['to_block'],
                current_block,
            )
            # filter the events and run callbacks
            self.filter_events(filters_unconfirmed, self.unconfirmed_callbacks)

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

    def filter_events(self, filter_params: Dict, name_to_callback: Dict):
        """ Filter events for given event names

        Params:
            filter_params: arguments for the filter call
            name_to_callback: dict that maps event name to callbacks executed
                if the event is emmited
        """
        for event_name, callback in name_to_callback.items():
            events = get_events(
                web3=self.web3,
                contract_manager=self.contract_manager,
                contract_name=self.contract_name,
                event_name=event_name,
                contract_address=self.contract_address,
                **filter_params,
            )
            for event in events:
                log.debug('Received confirmed %s event', event_name)
                callback(event)

    def _detected_chain_reorg(self, current_block: int):
        log.info(
            'Chain reorganization detected. '
            'Resyncing unconfirmed events (unconfirmed_head=%d) [@%d]' %
            (self.unconfirmed_head_number, current_block),
        )
        # here we should probably have a callback or a user-overriden method
        self.unconfirmed_head_number = self.confirmed_head_number
        self.unconfirmed_head_hash = self.confirmed_head_hash

    def reset_unconfirmed_on_reorg(self, current_block: int):
        """Test if chain reorganization happened (head number used in previous pass is greater than
        current_block parameter) and in that case reset unconfirmed event list."""
        if self.wait_sync_event.is_set():  # but not on first sync

            # block number increased or stayed the same
            if current_block >= self.unconfirmed_head_number:
                # if the hash of our head changed, there was a chain reorg
                current_unconfirmed_hash = self.web3.eth.getBlock(
                    self.unconfirmed_head_number,
                ).hash
                if current_unconfirmed_hash != self.unconfirmed_head_hash:
                    self._detected_chain_reorg(current_block)
            # block number decreased, there was a chain reorg
            elif current_block < self.unconfirmed_head_number:
                self._detected_chain_reorg(current_block)

            # now we have to check that the confirmed_head_hash stayed the same
            # otherwise the program aborts
            try:
                current_head_hash = self.web3.eth.getBlock(self.confirmed_head_number).hash
                if current_head_hash != self.confirmed_head_hash:
                    log.critical(
                        'Events considered confirmed have been reorganized. '
                        'Expected block hash %s for block number %d, but got block hash %s. '
                        "The BlockchainListener's number of required confirmations is %d.",
                        self.confirmed_head_hash,
                        self.confirmed_head_number,
                        current_head_hash,
                        self.required_confirmations,
                    )
                    sys.exit(1)  # unreachable as long as confirmation level is set high enough
            except AttributeError:
                log.critical(
                    'Events considered confirmed have been reorganized. '
                    'The block %d with hash %s does not exist any more.',
                    self.confirmed_head_number,
                    self.confirmed_head_hash,
                )
                sys.exit(1)  # unreachable as long as confirmation level is set high enough

    # filter for events after block_number
    # to_block is incremented because eth-tester doesn't include events from the end block
    # see https://github.com/raiden-network/raiden/pull/1321
    def get_filter_params(self, from_block: int, to_block: int) -> Dict[str, int]:
        assert from_block <= to_block
        return {
            'from_block': from_block + 1,
            'to_block': to_block + 1,
        }
