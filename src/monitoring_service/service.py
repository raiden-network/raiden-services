import sys
import time
from typing import Callable, List

import structlog
from web3 import Web3
from web3.middleware import construct_sign_and_send_raw_middleware

from monitoring_service.blockchain import BlockchainListener
from monitoring_service.constants import DEFAULT_REQUIRED_CONFIRMATIONS
from monitoring_service.database import Database
from monitoring_service.events import Event, ScheduledEvent
from monitoring_service.handlers import HANDLERS, Context
from raiden_contracts.constants import CONTRACT_MONITORING_SERVICE
from raiden_contracts.contract_manager import ContractManager
from raiden_libs.utils import private_key_to_address

log = structlog.get_logger(__name__)


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
        registry_address: str,
        monitor_contract_address: str,
        db_filename: str,
        sync_start_block: int = 0,
        required_confirmations: int = DEFAULT_REQUIRED_CONFIRMATIONS,
        poll_interval: int = 5,
    ):
        self.web3 = web3
        self.contract_manager = contract_manager
        self.private_key = private_key
        self.address = private_key_to_address(private_key)
        self.required_confirmations = required_confirmations
        self.poll_interval = poll_interval

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
        scheduled_events: List[ScheduledEvent] = list()

        self.bcl = BlockchainListener(
            web3=self.web3,
            contract_manager=contract_manager,
        )

        self.context = Context(
            ms_state=ms_state,
            db=self.database,
            scheduled_events=scheduled_events,
            w3=self.web3,
            contract_manager=contract_manager,
            last_known_block=0,
            monitoring_service_contract=monitoring_contract,
        )

    def start(self, wait_function: Callable = time.sleep) -> None:
        while True:
            last_block = self.web3.eth.blockNumber - self.required_confirmations
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

            # check triggered events
            # TODO: create a priority queue for this
            to_remove = []
            for scheduled_event in self.context.scheduled_events:
                event = scheduled_event.event

                if last_block >= scheduled_event.trigger_block_number:
                    to_remove.append(scheduled_event)
                    handle_event(event, self.context)

            for d in to_remove:
                self.context.scheduled_events.remove(d)

            if self.context.scheduled_events:
                log.info('Scheduled_events', events=self.context.scheduled_events)

            try:
                wait_function(self.poll_interval)
            except KeyboardInterrupt:
                log.info('Shutting down.')
                sys.exit(0)
