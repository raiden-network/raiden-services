import sys
import time
from typing import Callable, List

import structlog
from raiden_libs.utils import private_key_to_address
from web3 import Web3

from monitoring_service.blockchain import BlockchainListener
from monitoring_service.constants import DEFAULT_REQUIRED_CONFIRMATIONS
from monitoring_service.database import Database
from monitoring_service.events import Event, ScheduledEvent
from monitoring_service.handlers import HANDLERS, Context
from monitoring_service.states import BlockchainState, MonitoringServiceState
from raiden_contracts.contract_manager import ContractManager

log = structlog.get_logger(__name__)


def handle_event(event: Event, context: Context):
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

        chain_state = BlockchainState(
            token_network_registry_address=registry_address,
            monitor_contract_address=monitor_contract_address,
            latest_known_block=sync_start_block,
        )
        self.ms_state = MonitoringServiceState(
            blockchain_state=chain_state,
        )

        # TODO: tie database to chain id
        self.database = Database()
        self.scheduled_events: List[ScheduledEvent] = list()

        self.bcl = BlockchainListener(
            web3=self.web3,
            contract_manager=contract_manager,
        )

        self.context = Context(
            ms_state=self.ms_state,
            db=self.database,
            scheduled_events=self.scheduled_events,
            w3=self.web3,
            contract_manager=contract_manager,
            last_known_block=0,
        )

    def start(self, wait_function: Callable = time.sleep):
        while True:
            last_block = self.web3.eth.blockNumber - self.required_confirmations
            self.context.last_known_block = last_block

            # BCL return a new state and events related to channel lifecycle
            new_chain_state, events = self.bcl.get_events(
                chain_state=self.context.ms_state.blockchain_state,
                to_block=last_block,
            )

            self.context.ms_state.blockchain_state = new_chain_state
            for event in events:
                handle_event(event, self.context)

            # check triggered events
            # TODO: create a priority queue for this
            to_remove = []
            for scheduled_event in self.scheduled_events:
                event = scheduled_event.event

                if last_block >= scheduled_event.trigger_block_number:
                    to_remove.append(scheduled_event)
                    handle_event(event, self.context)

            for d in to_remove:
                self.scheduled_events.remove(d)

            if self.scheduled_events:
                log.info('Scheduled_events', events=self.scheduled_events)

            try:
                wait_function(self.poll_interval)
            except KeyboardInterrupt:
                log.info('Shutting down.')
                sys.exit(0)
