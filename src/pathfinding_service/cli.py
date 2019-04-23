"""Console script for pathfinding_service."""
from gevent import monkey, config  # isort:skip # noqa

# there were some issues with the 'thread' resolver, remove it from the options
config.resolver = ["dnspython", "ares", "block"]  # noqa
monkey.patch_all()  # isort:skip # noqa

from typing import Dict

import click
import structlog
from web3 import Web3
from web3.contract import Contract

from pathfinding_service.api import ServiceApi
from pathfinding_service.config import DEFAULT_API_HOST, DEFAULT_POLL_INTERVALL
from pathfinding_service.service import PathfindingService
from raiden.utils.typing import BlockNumber
from raiden_contracts.constants import CONTRACT_TOKEN_NETWORK_REGISTRY, CONTRACT_USER_DEPOSIT
from raiden_libs.cli import blockchain_options, common_options

log = structlog.get_logger(__name__)

DEFAULT_REQUIRED_CONFIRMATIONS = 8  # ~2min with 15s blocks


@blockchain_options(
    contracts_version="0.11.1", contracts=[CONTRACT_TOKEN_NETWORK_REGISTRY, CONTRACT_USER_DEPOSIT]
)
@click.command()
@click.option(
    "--host", default=DEFAULT_API_HOST, type=str, help="The host to use for serving the REST API"
)
@click.option(
    "--service-fee",
    default=0,
    type=click.IntRange(min=0),
    help="Service fee which is required before processing requests",
)
@click.option(
    "--confirmations",
    default=DEFAULT_REQUIRED_CONFIRMATIONS,
    type=click.IntRange(min=0),
    help="Number of block confirmations to wait for",
)
@click.option(
    "--enable-debug",
    default=False,
    is_flag=True,
    hidden=True,
    help="Number of block confirmations to wait for",
)
@common_options("raiden-pathfinding-service")
def main(
    private_key: str,
    state_db: str,
    web3: Web3,
    contracts: Dict[str, Contract],
    start_block: BlockNumber,
    confirmations: int,
    host: str,
    service_fee: int,
    enable_debug: bool,
) -> int:
    """ The Pathfinding service for the Raiden Network. """
    log.info("Starting Raiden Pathfinding Service")

    service = None
    api = None
    try:
        service = PathfindingService(
            web3=web3,
            contracts=contracts,
            sync_start_block=start_block,
            required_confirmations=confirmations,
            private_key=private_key,
            poll_interval=DEFAULT_POLL_INTERVALL,
            db_filename=state_db,
            service_fee=service_fee,
            debug_mode=enable_debug,
        )

        api = ServiceApi(service)
        api.run(host=host)

        service.run()
    except (KeyboardInterrupt, SystemExit):
        print("Exiting...")
    finally:
        log.info("Stopping Pathfinding Service...")
        if api:
            api.stop()
        if service:
            service.stop()

    return 0


if __name__ == "__main__":
    main(auto_envvar_prefix="PFS")  # pragma: no cover
