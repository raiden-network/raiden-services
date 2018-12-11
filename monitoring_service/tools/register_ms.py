import logging

import click
from eth_utils import is_address
from web3 import HTTPProvider, Web3

from monitoring_service.utils import is_service_registered, register_service
from raiden_libs.utils import get_private_key

log = logging.getLogger(__name__)


def validate_address(ctx, param, value):
    if is_address(value) is False:
        raise click.BadParameter('Must be a valid ethereum address')
    return value


def monitor_registration(
        web3: Web3,
        contract_manager,
        ms_contract_address,
        monitoring_service_address,
        private_key
):
    if is_service_registered(
        web3, contract_manager, ms_contract_address, monitoring_service_address
    ):
        log.error(
            'MS service %s is already registered in the contract %s' %
            (ms_contract_address, monitoring_service_address)
        )
        return False
    return register_service(web3, contract_manager, ms_contract_address, private_key)


@click.command()
@click.option(
    '--rpc-host',
    default='http://localhost:8545',
    help='address of the eth node'
)
@click.option(
    '--ms-contract-address',
    required=True,
    callback=validate_address,
    help='ethereum address of the MS contract'
)
@click.option(
    '--ms-address',
    required=True,
    callback=validate_address,
    help='Address of MS to register'
)
@click.option(
    '--private-key',
    required=True,
    help='Keystore path (raw-hex or JSON file)'
)
def main(
    rpc_host,
    ms_contract_address,
    ms_address,
    private_key
):
    web3 = Web3(HTTPProvider(rpc_host))
    private_key = get_private_key(private_key)
    return monitor_registration(web3, ms_contract_address, ms_address, private_key)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
