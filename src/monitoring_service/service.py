import sys
import time
from typing import Callable

import structlog
from web3 import Web3
from web3.middleware import construct_sign_and_send_raw_middleware

from monitoring_service.blockchain import BlockchainListener
from monitoring_service.constants import (
    DEFAULT_GAS_BUFFER_FACTOR,
    DEFAULT_GAS_CHECK_BLOCKS,
    DEFAULT_REQUIRED_CONFIRMATIONS,
    MAX_FILTER_INTERVAL,
)
from monitoring_service.database import Database
from monitoring_service.events import Event
from monitoring_service.handlers import HANDLERS, Context
from raiden.utils.typing import Address, BlockNumber
from raiden_contracts.constants import CONTRACT_MONITORING_SERVICE, GAS_REQUIRED_FOR_MS_MONITOR
from raiden_contracts.contract_manager import ContractManager
from raiden_libs.utils import private_key_to_address

log = structlog.get_logger(__name__)


def check_gas_reserve(web3: Web3, private_key: str) -> None:
    """ Check periodically for gas reserve in the account """
    gas_price = web3.eth.gasPrice
    gas_limit = GAS_REQUIRED_FOR_MS_MONITOR
    estimated_required_balance = gas_limit * gas_price * DEFAULT_GAS_BUFFER_FACTOR
    estimated_required_balance_eth = Web3.fromWei(estimated_required_balance, 'ether')
    current_balance = web3.eth.getBalance(private_key_to_address(private_key))
    if current_balance < estimated_required_balance:
        log.error(
            "Your account's balance is below the estimated gas reserve of "
            f"{estimated_required_balance_eth} Eth. You will be be unable "
            "to perform on-chain transactions and cannot monitor any channels. "
            "Please add funds to your account as soon as possible.",
        )


def handle_event(event: Event, context: Context) -> None:
    log.debug('Processing event', event_=event)
    handler: Callable = HANDLERS[type(event)]
    handler(event, context)


class MonitoringService:
    def __init__(
        self,
        web3: Web3,
        contract_manager: ContractManager,
        private_key: str,
        registry_address: Address,
        monitor_contract_address: Address,
        db_filename: str,
        sync_start_block: BlockNumber = 0,
        required_confirmations: int = DEFAULT_REQUIRED_CONFIRMATIONS,
        poll_interval: float = 1,
    ):
        self.web3 = web3
        self.contract_manager = contract_manager
        self.private_key = private_key
        self.address = private_key_to_address(private_key)
        self.required_confirmations = required_confirmations
        self.poll_interval = poll_interval
        self.last_gas_check_block = 0

        web3.middleware_stack.add(
            construct_sign_and_send_raw_middleware(private_key),
        )

        monitoring_contract = self.web3.eth.contract(
            abi=self.contract_manager.get_contract_abi(
                CONTRACT_MONITORING_SERVICE,
            ),
            address=monitor_contract_address,
        )

        chain_id = int(web3.net.version)
        self.database = Database(
            filename=db_filename,
            chain_id=chain_id,
            registry_address=registry_address,
            receiver=self.address,
            msc_address=monitor_contract_address,
        )
        ms_state = self.database.load_state(sync_start_block)

        self.bcl = BlockchainListener(
            web3=self.web3,
            contract_manager=contract_manager,
        )

        self.context = Context(
            ms_state=ms_state,
            db=self.database,
            scheduled_events=list(),
            w3=self.web3,
            contract_manager=contract_manager,
            last_known_block=0,
            monitoring_service_contract=monitoring_contract,
        )

    def start(
        self,
        wait_function: Callable = time.sleep,
        check_account_gas_reserve: bool = True,
    ) -> None:
        while True:
            last_confirmed_block = self.web3.eth.blockNumber - self.required_confirmations

            # check gas reserve
            do_gas_reserve_check = (
                check_account_gas_reserve and
                last_confirmed_block >= self.last_gas_check_block + DEFAULT_GAS_CHECK_BLOCKS
            )
            if do_gas_reserve_check:
                check_gas_reserve(self.web3, self.private_key)
                self.last_gas_check_block = last_confirmed_block

            last_query_interval_block = (
                self.context.ms_state.blockchain_state.latest_known_block + MAX_FILTER_INTERVAL
            )
            # Limit the max number of blocks that is processed per iteration
            last_block = min(last_confirmed_block, last_query_interval_block)

            self._process_new_blocks(last_block)

            try:
                wait_function(self.poll_interval)
            except KeyboardInterrupt:
                log.info('Shutting down.')
                sys.exit(0)

    def _process_new_blocks(self, last_block: BlockNumber) -> None:
        self.context.last_known_block = last_block

        # BCL return a new state and events related to channel lifecycle
        new_chain_state, events = self.bcl.get_events(
            chain_state=self.context.ms_state.blockchain_state,
            to_block=last_block,
        )

        # If a new token network was found we need to write it to the DB, otherwise
        # the constraints for new channels will not be constrained. But only update
        # the network addresses here, all else is done later.
        token_networks_changed = (
            self.context.ms_state.blockchain_state.token_network_addresses !=
            new_chain_state.token_network_addresses
        )
        if token_networks_changed:
            self.context.ms_state.blockchain_state.token_network_addresses = \
                new_chain_state.token_network_addresses
            self.context.db.update_state(self.context.ms_state)

        # Now set the updated chain state to the context, will be stored later
        self.context.ms_state.blockchain_state = new_chain_state
        for event in events:
            handle_event(event, self.context)

        # check triggered events and trigger the correct ones
        for scheduled_event in self.context.scheduled_events.copy():
            event = scheduled_event.event

            if last_block >= scheduled_event.trigger_block_number:
                self.context.scheduled_events.remove(scheduled_event)
                handle_event(event, self.context)

        if self.context.scheduled_events:
            log.debug('Scheduled_events', events=self.context.scheduled_events)

        # check pending transactions
        # this is done here so we don't have to block waiting for receipts in the state machine
        for tx_hash in self.context.db.get_waiting_transactions():
            receipt = self.web3.eth.getTransactionReceipt(tx_hash)

            if receipt is not None:
                self.context.db.remove_waiting_transaction(tx_hash)

                if receipt['status'] == 1:
                    log.info(
                        'Transaction was mined successfully',
                        transaction_hash=tx_hash,
                        receipt=receipt,
                    )
                else:
                    log.error(
                        'Transaction was not mined successfully',
                        transaction_hash=tx_hash,
                        receipt=receipt,
                    )
