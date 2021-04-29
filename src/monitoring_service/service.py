import sys
from datetime import datetime
from typing import Dict

import gevent
import sentry_sdk
import structlog
from eth_typing import Hash32
from eth_utils import to_canonical_address
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import TransactionNotFound
from web3.middleware import construct_sign_and_send_raw_middleware

from monitoring_service import metrics
from monitoring_service.constants import (
    DEFAULT_GAS_BUFFER_FACTOR,
    DEFAULT_GAS_CHECK_BLOCKS,
    KEEP_MRS_WITHOUT_CHANNEL,
)
from monitoring_service.database import Database
from monitoring_service.handlers import HANDLERS, Context
from raiden.utils.typing import BlockNumber, BlockTimeout, ChainID, MonitoringServiceAddress
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_SERVICE_REGISTRY,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_contracts.contract_manager import gas_measurements
from raiden_contracts.utils.type_aliases import PrivateKey
from raiden_libs.blockchain import get_blockchain_events_adaptive
from raiden_libs.events import Event
from raiden_libs.utils import private_key_to_address

log = structlog.get_logger(__name__)


def check_gas_reserve(web3: Web3, private_key: PrivateKey) -> None:
    """Check periodically for gas reserve in the account"""
    gas_price = web3.eth.gasPrice
    gas_limit = gas_measurements()["MonitoringService.monitor"]
    estimated_required_balance = gas_limit * gas_price * DEFAULT_GAS_BUFFER_FACTOR
    estimated_required_balance_eth = Web3.fromWei(estimated_required_balance, "ether")
    current_balance = web3.eth.getBalance(private_key_to_address(private_key))
    if current_balance < estimated_required_balance:
        log.error(
            "Your account's balance is below the estimated gas reserve of "
            f"{estimated_required_balance_eth} Eth. You will be be unable "
            "to perform on-chain transactions and cannot monitor any channels. "
            "Please add funds to your account as soon as possible."
        )
        metrics.get_metrics_for_label(
            metrics.ERRORS_LOGGED, metrics.ErrorCategory.BLOCKCHAIN
        ).inc()


def handle_event(event: Event, context: Context) -> None:
    """Calls the handler for the given event.

    Exceptions are caught and generate both error logs and sentry issues.
    Events are not retried after an exception.
    """
    log.debug(
        "Processing event",
        event_=event,
        latest_confirmed_block=context.latest_confirmed_block,
        latest_unconfirmed_block=context.get_latest_unconfirmed_block(),
    )
    handler = HANDLERS.get(type(event))

    if handler:
        with sentry_sdk.push_scope() as sentry_scope:
            sentry_scope.set_tag("event", event.__class__.__name__)
            try:
                with metrics.collect_event_metrics(event):
                    handler(event, context)
                log.debug(
                    "Processed event",
                    num_scheduled_events=context.database.scheduled_event_count(),
                )
            except Exception as ex:  # pylint: disable=broad-except
                log.error("Error during event handler", handled_event=event, exc_info=ex)
                sentry_sdk.capture_exception(ex)


class MonitoringService:
    # pylint: disable=too-few-public-methods,too-many-instance-attributes
    def __init__(  # pylint: disable=too-many-arguments
        self,
        web3: Web3,
        private_key: PrivateKey,
        db_filename: str,
        contracts: Dict[str, Contract],
        sync_start_block: BlockNumber,
        required_confirmations: BlockTimeout,
        poll_interval: float,
        min_reward: int = 0,
    ):
        self.web3 = web3
        self.chain_id = ChainID(web3.eth.chainId)
        self.private_key = private_key
        self.address = private_key_to_address(private_key)
        self.poll_interval = poll_interval
        self.service_registry = contracts[CONTRACT_SERVICE_REGISTRY]
        self.token_network_registry = contracts[CONTRACT_TOKEN_NETWORK_REGISTRY]

        web3.middleware_onion.add(construct_sign_and_send_raw_middleware(private_key))

        monitoring_contract = contracts[CONTRACT_MONITORING_SERVICE]
        user_deposit_contract = contracts[CONTRACT_USER_DEPOSIT]

        self.database = Database(
            filename=db_filename,
            chain_id=self.chain_id,
            registry_address=to_canonical_address(self.token_network_registry.address),
            receiver=self.address,
            msc_address=MonitoringServiceAddress(
                to_canonical_address(monitoring_contract.address)
            ),
            sync_start_block=sync_start_block,
        )
        ms_state = self.database.load_state()

        self.context = Context(
            ms_state=ms_state,
            database=self.database,
            web3=self.web3,
            monitoring_service_contract=monitoring_contract,
            user_deposit_contract=user_deposit_contract,
            min_reward=min_reward,
            required_confirmations=required_confirmations,
        )

    def start(self) -> None:
        if not self.service_registry.functions.hasValidRegistration(self.address).call():
            log.error("No valid registration in ServiceRegistry", address=self.address)
            sys.exit(1)

        last_gas_check_block = 0
        while True:
            last_confirmed_block = self.context.latest_confirmed_block

            # check gas reserve
            do_gas_reserve_check = (
                last_confirmed_block >= last_gas_check_block + DEFAULT_GAS_CHECK_BLOCKS
            )
            if do_gas_reserve_check:
                check_gas_reserve(self.web3, self.private_key)
                last_gas_check_block = last_confirmed_block

            self._process_new_blocks(latest_confirmed_block=last_confirmed_block)
            self._trigger_scheduled_events()
            self._check_pending_transactions()
            self._purge_old_monitor_requests()

            gevent.sleep(self.poll_interval)

    def _process_new_blocks(self, latest_confirmed_block: BlockNumber) -> None:
        token_network_addresses = self.context.database.get_token_network_addresses()

        events = get_blockchain_events_adaptive(
            web3=self.web3,
            blockchain_state=self.context.ms_state.blockchain_state,
            token_network_addresses=token_network_addresses,
            latest_confirmed_block=latest_confirmed_block,
        )

        if events is None:
            return

        for event in events:
            handle_event(event, self.context)

    def _trigger_scheduled_events(self) -> None:
        """Trigger scheduled events

        Here `latest_block` is used instead of `latest_confirmed_block`, because triggered
        events only rely on block number, and not on certain events that might change during
        a chain reorg.
        """
        triggered_events = self.context.database.get_scheduled_events(
            max_trigger_block=self.context.get_latest_unconfirmed_block()
        )
        for scheduled_event in triggered_events:
            event = scheduled_event.event

            handle_event(event, self.context)
            self.context.database.remove_scheduled_event(scheduled_event)

    def _check_pending_transactions(self) -> None:
        """Checks if pending transaction have been mined and confirmed.

        This is done here so we don't have to block waiting for receipts in the state machine.

        In theory it's not necessary to check all pending transactions, but only the one with the
        smallest nonce, and continue from there when this one is mined and confirmed. However,
        as it is not expected that this list becomes to big this isn't optimized currently.
        """
        for tx_hash in self.context.database.get_waiting_transactions():
            try:
                receipt = self.web3.eth.getTransactionReceipt(Hash32(tx_hash))
            except TransactionNotFound:
                continue

            tx_block = receipt.get("blockNumber")
            if tx_block is None:
                continue

            confirmation_block = tx_block + self.context.required_confirmations
            if self.web3.eth.blockNumber < confirmation_block:
                continue

            self.context.database.remove_waiting_transaction(tx_hash)
            if receipt["status"] == 1:
                log.info(
                    "Transaction was mined successfully",
                    transaction_hash=tx_hash,
                    receipt=receipt,
                )
            else:
                log.error(
                    "Transaction was not mined successfully",
                    transaction_hash=tx_hash,
                    receipt=receipt,
                )

    def _purge_old_monitor_requests(self) -> None:
        """Delete all old MRs for which still no channel exists.

        Also marks all MRs which have a channel as not waiting_for_channel to
        avoid checking them again, every time.
        """
        with self.context.database.conn:
            self.context.database.conn.execute(
                """
                UPDATE monitor_request SET waiting_for_channel = 0
                WHERE waiting_for_channel
                  AND EXISTS (
                    SELECT 1
                    FROM channel
                    WHERE channel.identifier = monitor_request.channel_identifier
                      AND channel.token_network_address = monitor_request.token_network_address
                  )
            """
            )
            before_this_is_old = datetime.utcnow() - KEEP_MRS_WITHOUT_CHANNEL
            self.context.database.conn.execute(
                """
                DELETE FROM monitor_request
                WHERE waiting_for_channel
                  AND saved_at < ?
            """,
                [before_this_is_old],
            )
