import sys
from time import sleep
from typing import Dict, List

import structlog
from web3 import HTTPProvider, Web3

from monitoring_service.blockchain import BlockchainListener
from monitoring_service.database import Database
from monitoring_service.events import Event, ScheduledEvent
from monitoring_service.handlers import HANDLERS, Context, EventHandler
from monitoring_service.states import MonitoringServiceState
from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path

contract_manager = ContractManager(contracts_precompiled_path())
log = structlog.get_logger(__name__)


def handle_event(handlers: Dict, event: Event):
    log.debug('Processing event:', event_=event)
    handler: EventHandler = handlers[type(event)]
    handler.handle_event(event)


def main():
    ms_state = MonitoringServiceState(
        token_network_registry_address='0x40a5D15fD98b9a351855D64daa9bc621F400cbc5',
        monitor_contract_address='',
        latest_known_block=0,
    )
    # TODO: tie databsae to chain id
    database = Database()
    scheduled_events: List[ScheduledEvent] = list()

    provider = HTTPProvider('http://parity.ropsten.ethnodes.brainbot.com:8545')
    w3 = Web3(provider)
    bcl = BlockchainListener(
        web3=w3,
        contract_manager=contract_manager,
    )

    context = Context(
        ms_state=ms_state,
        db=database,
        scheduled_events=scheduled_events,
        w3=w3,
        contract_manager=contract_manager,
        last_known_block=0,
    )

    handlers = {
        event: handler(context) for event, handler in HANDLERS.items()
    }

    while True:
        last_block = w3.eth.blockNumber - 5
        context.last_known_block = last_block
        for e in bcl.get_events(context, last_block):
            handle_event(handlers, e)

        # check triggered events
        # TODO: create a priority scheduled_events for this
        to_remove = []
        for scheduled_event in scheduled_events:
            event = scheduled_event.event

            if last_block >= scheduled_event.trigger_block_number:
                to_remove.append(scheduled_event)
                handle_event(handlers, event)

        for d in to_remove:
            scheduled_events.remove(d)

        if scheduled_events:
            log.info('scheduled_events', events=scheduled_events)

        try:
            sleep(1)
        except KeyboardInterrupt:
            log.info('Shutting down.')
            sys.exit(0)


if __name__ == '__main__':
    main()
