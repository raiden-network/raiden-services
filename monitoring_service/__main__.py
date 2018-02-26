import click
import logging
from monitoring_service import MonitoringService
from monitoring_service.transport import MatrixTransport
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
def main(
    private_key,
    monitoring_channel,
    matrix_homeserver,
    matrix_username,
    matrix_password,
    rest_host,
    rest_port
):
    transport = MatrixTransport(
        matrix_homeserver,
        matrix_username,
        matrix_password,
        monitoring_channel
    )
    blockchain = BlockchainMonitor()

    monitor = MonitoringService(
        private_key,
        transport,
        blockchain
    )

    api = ServiceApi(monitor, blockchain)
    api.run(rest_host, rest_port)

    monitor.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARN)
    with no_ssl_verification():
        main()
