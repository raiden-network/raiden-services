"""Console script for pathfinding_service."""
from gevent import monkey, config  # isort:skip # noqa

# there were some issues with the 'thread' resolver, remove it from the options
config.resolver = ['dnspython', 'ares', 'block']  # noqa
monkey.patch_all()  # isort:skip # noqa

import click
import structlog
from web3 import Web3

from pathfinding_service import PathfindingService
from pathfinding_service.api import ServiceApi
from pathfinding_service.config import DEFAULT_API_HOST, DEFAULT_POLL_INTERVALL
from raiden_contracts.constants import CONTRACT_TOKEN_NETWORK_REGISTRY, CONTRACT_USER_DEPOSIT
from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path
from raiden_libs.cli import blockchain_options, common_options
from raiden_libs.contract_info import START_BLOCK_ID

log = structlog.get_logger(__name__)
contract_manager = ContractManager(contracts_precompiled_path())

DEFAULT_REQUIRED_CONFIRMATIONS = 8  # ~2min with 15s blocks


@blockchain_options(
    contracts_version='0.10.1', contracts=[CONTRACT_TOKEN_NETWORK_REGISTRY, CONTRACT_USER_DEPOSIT]
)
@click.command()
@click.option(
    '--host', default=DEFAULT_API_HOST, type=str, help='The host to use for serving the REST API'
)
@click.option(
    '--service-fee',
    default=0,
    type=click.IntRange(min=0),
    help='Service fee which is required before processing requests',
)
@click.option(
    '--confirmations',
    default=DEFAULT_REQUIRED_CONFIRMATIONS,
    type=click.IntRange(min=0),
    help='Number of block confirmations to wait for',
)
@common_options('raiden-pathfinding-service')
def main(
    private_key: str,
    state_db: str,
    web3: Web3,
    contract_infos: dict,
    confirmations: int,
    host: str,
    service_fee: int,
) -> int:
    """ The Pathfinding service for the Raiden Network. """
    log.info("Starting Raiden Pathfinding Service")

    service = None
    api = None
    try:
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
