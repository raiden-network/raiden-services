from gevent import monkey  # isort:skip # noqa
monkey.patch_all()  # isort:skip # noqa

import json
import logging
import logging.config
import os
import sys
from typing import TextIO

import click
from eth_utils import is_checksum_address
from requests.exceptions import ConnectionError
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


def setup_logging(log_level: str, log_config: TextIO):
    """ Set log level and (optionally) detailed JSON logging config """
    # import pdb; pdb.set_trace()
    level = getattr(logging, log_level)
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%m-%d %H:%M:%S',
    )

    if log_config:
        config = json.load(log_config)
        logging.config.dictConfig(config)


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
    default='0x1111111111111111111111111111111111111111',
    callback=validate_address,
)
@click.option(
    '--state-db',
    default=os.path.join(click.get_app_dir('raiden-monitoring-service'), 'state.db'),
    type=str,
    help='state DB to save received balance proofs to',
)
@click.option(
    '--log-level',
    default='INFO',
    type=click.Choice(['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']),
    help='Print log messages of this level and more important ones',
)
@click.option(
    '--log-config',
    type=click.File('r'),
    help='Use the given JSON file for logging configuration',
)
def main(
    private_key: str,
    monitoring_channel: str,
    matrix_homeserver: str,
    matrix_username: str,
    matrix_password: str,
    eth_rpc: str,
    registry_address: Address,
    start_block: int,
    confirmations: int,
    monitor_contract_address: Address,
    state_db: str,
    log_level: str,
    log_config: TextIO,
):
    """Console script for monitoring_service.

    Logging can be quickly set by specifying a global log level or in a
    detailed way by using a log configuration file. See
    https://docs.python.org/3.7/library/logging.config.html#logging-config-dictschema
    for a detailed description of the format.
    """
    assert log_config is None
    setup_logging(log_level, log_config)

    log.info("Starting Raiden Monitoring Service")

    contracts_version = 'pre_limits'
    log.debug(f'Using contracts version: {contracts_version}')

    try:
        log.info(f'Starting Web3 client for node at {eth_rpc}')
        provider = HTTPProvider(eth_rpc)
        web3 = Web3(provider)
        int(web3.net.version)  # Will throw ConnectionError on bad Ethereum client
    except ConnectionError:
        log.error(
            'Can not connect to the Ethereum client. Please check that it is running and that '
            'your settings are correct.',
        )
        sys.exit(1)

    app_dir = click.get_app_dir('raiden-monitoring-service')
    if os.path.isdir(app_dir) is False:
        os.makedirs(app_dir)

    transport = MatrixTransport(
        matrix_homeserver,
        matrix_username,
        matrix_password,
        monitoring_channel,
    )

    database = StateDBSqlite(state_db)

    service = None
    try:
        service = MonitoringService(
            web3=web3,
            contract_manager=contract_manager,
            private_key=private_key,
            state_db=database,
            transport=transport,
            registry_address=registry_address,
            monitor_contract_address=monitor_contract_address,
        )

        service.run()
    except (KeyboardInterrupt, SystemExit):
        print('Exiting...')
    finally:
        log.info('Stopping Pathfinding Service...')
        if service:
            service.stop()

    return 0


if __name__ == "__main__":
    main(auto_envvar_prefix='MS')  # pragma: no cover
