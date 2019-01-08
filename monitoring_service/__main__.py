import logging
import os

import click
from eth_utils import is_checksum_address
from web3 import HTTPProvider, Web3

from monitoring_service import MonitoringService
from monitoring_service.state_db import StateDBSqlite
from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path
from raiden_libs.transport import MatrixTransport
from raiden_libs.types import Address

log = logging.getLogger(__name__)
contract_manager = ContractManager(contracts_precompiled_path())

DEFAULT_REQUIRED_CONFIRMATIONS = 8


def validate_address(ctx, param, value):
    if value is None:
        # None as default value allowed
        return None
    if not is_checksum_address(value):
        raise click.BadParameter('not an EIP-55 checksummed address')
    return value


@click.command()
@click.option(
    '--private-key',
    default=None,
    required=True,
    help='Private key to use (the address should have enough ETH balance to send transactions)',
)
@click.option(
    '--monitoring-channel',
    default='#monitor_test:transport01.raiden.network',
    help='Location of the monitoring channel to connect to',
)
@click.option(
    '--matrix-homeserver',
    default='https://transport01.raiden.network',
    help='Matrix username',
)
@click.option(
    '--matrix-username',
    default=None,
    required=True,
    help='Matrix username',
)
@click.option(
    '--matrix-password',
    default=None,
    required=True,
    help='Matrix password',
)
@click.option(
    '--rest-host',
    default='localhost',
    type=str,
    help='REST service endpoint',
)
@click.option(
    '--rest-port',
    default=5001,
    type=int,
    help='REST service endpoint',
)
@click.option(
    '--eth-rpc',
    default='http://localhost:8545',
    type=str,
    help='Ethereum node RPC URI',
)
@click.option(
    '--registry-address',
    type=str,
    help='Address of the token network registry',
    callback=validate_address,
)
@click.option(
    '--start-block',
    default=0,
    type=click.IntRange(min=0),
    help='Block to start syncing at',
)
@click.option(
    '--confirmations',
    default=DEFAULT_REQUIRED_CONFIRMATIONS,
    type=click.IntRange(min=0),
    help='Number of block confirmations to wait for',
)
@click.option(
    '--monitor-contract-address',
    type=str,
    help='Address of the token monitor contract',
    default='',
    callback=validate_address,
)
@click.option(
    '--state-db',
    default=os.path.join(click.get_app_dir('raiden-monitoring-service'), 'state.db'),
    type=str,
    help='state DB to save received balance proofs to',
)
def main(
    private_key,
    monitoring_channel,
    matrix_homeserver,
    matrix_username,
    matrix_password,
    rest_host,
    rest_port,
    eth_rpc,
    registry_address: Address,
    start_block: int,
    confirmations: int,
    monitor_contract_address: Address,
    state_db: str,
):
    log.info("Starting Raiden Monitoring Service")

    contracts_version = 'pre_limits'
    log.debug(f'Using contracts version: {contracts_version}')

    app_dir = click.get_app_dir('raiden-monitoring-service')
    if os.path.isdir(app_dir) is False:
        os.makedirs(app_dir)

    transport = MatrixTransport(
        matrix_homeserver,
        matrix_username,
        matrix_password,
        monitoring_channel,
    )

    web3 = Web3(HTTPProvider(eth_rpc))
    # blockchain = BlockchainMonitor(web3, contract_manager)
    database = StateDBSqlite(state_db)

    monitor = MonitoringService(
        web3=web3,
        contract_manager=contract_manager,
        private_key=private_key,
        state_db=database,
        transport=transport,
        registry_address=registry_address,
        monitor_contract_address=monitor_contract_address,
    )

    # api = ServiceApi(monitor, blockchain)
    # api.run(rest_host, rest_port)

    monitor.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARN)
    main()
