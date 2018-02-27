import click
import logging
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
    '--state-db',
    default=click.get_app_dir('raiden-monitoring-service'),
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
    state_db
):
    transport = MatrixTransport(
        matrix_homeserver,
        matrix_username,
        matrix_password,
        monitoring_channel
    )
    blockchain = BlockchainMonitor()
    state_db = StateDB()

    monitor = MonitoringService(
        private_key,
        state_db=state_db,
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
