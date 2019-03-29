"""Console script for pathfinding_service."""
from gevent import monkey, config  # isort:skip # noqa
# there were some issues with the 'thread' resolver, remove it from the options
config.resolver = ['dnspython', 'ares', 'block'] # noqa
monkey.patch_all()  # isort:skip # noqa

import sys

import click
import structlog
from requests.exceptions import ConnectionError
from web3 import HTTPProvider, Web3
from web3.middleware import geth_poa_middleware

from pathfinding_service import PathfindingService
from pathfinding_service.api.rest import ServiceApi
from pathfinding_service.config import DEFAULT_API_HOST, DEFAULT_POLL_INTERVALL
from pathfinding_service.middleware import http_retry_with_backoff_middleware
from raiden.utils.typing import BlockNumber, ChainID
from raiden_contracts.constants import CONTRACT_TOKEN_NETWORK_REGISTRY, CONTRACT_USER_DEPOSIT
from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path
from raiden_libs.cli import blockchain_options, common_options
from raiden_libs.contract_info import START_BLOCK_ID, get_contract_addresses_and_start_block
from raiden_libs.types import Address

log = structlog.get_logger(__name__)
contract_manager = ContractManager(contracts_precompiled_path())


@click.command()
@click.option(
    '--host',
    default=DEFAULT_API_HOST,
    type=str,
    help='The host to use for serving the REST API',
)
@click.option(
    '--service-fee',
    default=0,
    type=click.IntRange(min=0),
    help='Service fee which is required before processing requests',
)
@common_options('raiden-pathfinding-service')
@blockchain_options
def main(
    private_key: str,
    state_db: str,
    eth_rpc: str,
    registry_address: Address,
    user_deposit_contract_address: Address,
    start_block: BlockNumber,
    confirmations: int,
    host: str,
    service_fee: int,
):
    """Console script for pathfinding_service.

    Logging can be quickly set by specifying a global log level or in a
    detailed way by using a log configuration file. See
    https://docs.python.org/3.7/library/logging.config.html#logging-config-dictschema
    for a detailed description of the format.
    """
    log.info("Starting Raiden Pathfinding Service")

    contracts_version = '0.10.1'
    log.info(f'Using contracts version: {contracts_version}')

    try:
        log.info(f'Starting Web3 client for node at {eth_rpc}')
        provider = HTTPProvider(eth_rpc)
        web3 = Web3(provider)
        # Will throw ConnectionError on bad Ethereum client
        net_version = ChainID(int(web3.net.version))
    except ConnectionError:
        log.error(
            'Can not connect to the Ethereum client. Please check that it is running and that '
            'your settings are correct.',
        )
        sys.exit(1)

    # Add POA middleware for geth POA chains, no/op for other chains
    web3.middleware_stack.inject(geth_poa_middleware, layer=0)

    # give web3 some time between retries before failing
    provider.middlewares.replace(
        'http_retry_request',
        http_retry_with_backoff_middleware,
    )

    contract_infos = get_contract_addresses_and_start_block(
        chain_id=net_version,
        contracts_version=contracts_version,
        token_network_registry_address=registry_address,
        # necessary so that the overwrite logic works properly
        monitor_contract_address=Address('0x' + '1' * 40),
        user_deposit_contract_address=user_deposit_contract_address,
        start_block=start_block,
    )

    if contract_infos is None:
        log.critical('Could not find correct contracts to use. Please check your configuration')
        sys.exit(1)
    else:
        log.info(
            'Contract information',
            registry_address=contract_infos[CONTRACT_TOKEN_NETWORK_REGISTRY],
            user_deposit_contract_address=contract_infos[CONTRACT_USER_DEPOSIT],
            sync_start_block=contract_infos[START_BLOCK_ID],
        )

    service = None
    api = None
    try:
        log.info('Starting Pathfinding Service...')
        service = PathfindingService(
            web3=web3,
            contract_manager=contract_manager,
            registry_address=contract_infos[CONTRACT_TOKEN_NETWORK_REGISTRY],
            user_deposit_contract_address=contract_infos[CONTRACT_USER_DEPOSIT],
            sync_start_block=contract_infos[START_BLOCK_ID],
            required_confirmations=confirmations,
            private_key=private_key,
            poll_interval=DEFAULT_POLL_INTERVALL,
            db_filename=state_db,
            service_fee=service_fee,
        )

        api = ServiceApi(service)
        api.run(host=host)

        service.run()
    except (KeyboardInterrupt, SystemExit):
        print('Exiting...')
    finally:
        log.info('Stopping Pathfinding Service...')
        if api:
            api.stop()
        if service:
            service.stop()

    return 0


if __name__ == "__main__":
    main(auto_envvar_prefix='PFS')  # pragma: no cover
