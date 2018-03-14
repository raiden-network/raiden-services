import click
import os
import logging
from web3 import Web3, HTTPProvider

from monitoring_service import MonitoringService
from monitoring_service.transport import MatrixTransport
from monitoring_service.state_db import StateDB
from monitoring_service.no_ssl_patch import no_ssl_verification
from monitoring_service.api.rest import ServiceApi
from monitoring_service.blockchain import BlockchainMonitor


@click.command()
@click.option(
    '--private-key',
    default=None,
    required=True,
    help='Private key to use (the address should have enough ETH balance to send transactions)'
)
@click.option(
    '--monitoring-channel',
    default='#monitor_test:transport01.raiden.network',
    help='Location of the monitoring channel to connect to'
)
@click.option(
    '--matrix-homeserver',
    default='https://transport01.raiden.network',
    help='Matrix username'
)
@click.option(
    '--matrix-username',
    default=None,
    required=True,
    help='Matrix username'
)
@click.option(
    '--matrix-password',
    default=None,
    required=True,
    help='Matrix password'
)
@click.option(
    '--rest-host',
    default='localhost',
    type=str,
    help='REST service endpoint'
)
@click.option(
    '--rest-port',
    default=5001,
    type=int,
    help='REST service endpoint'
)
@click.option(
    '--eth-rpc',
    default='http://localhost:8545',
    type=str,
    help='Ethereum node RPC URI'
)
@click.option(
    '--state-db',
    default=os.path.join(click.get_app_dir('raiden-monitoring-service'), 'state.db'),
    type=str,
    help='state DB to save received balance proofs to'
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
    state_db
):
    app_dir = click.get_app_dir('raiden-monitoring-service')
    if os.path.isdir(app_dir) is False:
        os.makedirs(app_dir)
    transport = MatrixTransport(
        matrix_homeserver,
        matrix_username,
        matrix_password,
        monitoring_channel
    )
    web3 = Web3(HTTPProvider(eth_rpc))
    blockchain = BlockchainMonitor(web3)
    db = StateDB(state_db)

    monitor = MonitoringService(
        private_key,
        state_db=db,
        transport=transport,
        blockchain=blockchain
    )

    api = ServiceApi(monitor, blockchain)
    api.run(rest_host, rest_port)

    monitor.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARN)
    with no_ssl_verification():
        main()
