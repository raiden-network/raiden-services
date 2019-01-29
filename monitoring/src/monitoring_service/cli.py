import sys
import time
from typing import Callable, List

import structlog
from web3 import HTTPProvider, Web3

from monitoring_service.blockchain import BlockchainListener
from monitoring_service.database import Database
from monitoring_service.events import Event, ScheduledEvent
from monitoring_service.handlers import HANDLERS, Context
from monitoring_service.states import MonitoringServiceState
from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path

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
        registry_address: str = '0x40a5D15fD98b9a351855D64daa9bc621F400cbc5',
        monitor_contract_address: str = '',
        sync_start_block: int = 0,
        required_confirmations: int = 8,
        poll_interval: int = 1,
    ):
        self.web3 = web3
        self.contract_manager = contract_manager
        self.private_key = private_key
        self.required_confirmations = required_confirmations
        self.poll_interval = poll_interval

        self.ms_state = MonitoringServiceState(
            token_network_registry_address=registry_address,
            monitor_contract_address=monitor_contract_address,
            latest_known_block=sync_start_block,
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

            for event in self.bcl.get_events(self.context, last_block):
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


def main():
    provider = HTTPProvider('http://parity.ropsten.ethnodes.brainbot.com:8545')
    w3 = Web3(provider)

    contract_manager = ContractManager(contracts_precompiled_path())

    ms = MonitoringService(
        web3=w3,
        contract_manager=contract_manager,
        private_key='',
    )

    ms.start()


if __name__ == '__main__':
    main()
