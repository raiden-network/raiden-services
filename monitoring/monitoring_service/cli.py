from pprint import pprint

from web3 import HTTPProvider, Web3

from monitoring_service.blockchain import BlockchainListener
from monitoring_service.database import Database
from monitoring_service.handlers import HANDLERS, Context, EventHandler
from monitoring_service.states import MonitoringServiceState
from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path

contract_manager = ContractManager(contracts_precompiled_path())


def main():
    ms_state = MonitoringServiceState(
        token_network_registry_address='0x40a5D15fD98b9a351855D64daa9bc621F400cbc5',
        latest_known_block=0,
    )
    database = Database()

    context = Context(ms_state=ms_state, db=database)

    handlers = {
        event: handler(context) for event, handler in HANDLERS.items()
    }

    pprint(handlers)

    provider = HTTPProvider('http://parity.ropsten.ethnodes.brainbot.com:8545')
    w3 = Web3(provider)
    print('Startup finished')
    bcl = BlockchainListener(web3=w3, contract_manager=contract_manager)

    last_block = w3.eth.blockNumber - 5
    print('Last block', last_block)
    for e in bcl.get_events(context, last_block):
        print('> Current event:', e)
        handler: EventHandler = handlers[type(e)]
        handler.handle_event(e)

    pprint(database.channels)


if __name__ == '__main__':
    main()
