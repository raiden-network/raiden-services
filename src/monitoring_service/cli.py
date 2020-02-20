from typing import Dict

import click
import structlog
from eth_utils import to_checksum_address
from web3 import Web3
from web3.contract import Contract

from monitoring_service.service import MonitoringService
from raiden.settings import DEFAULT_NUMBER_OF_BLOCK_CONFIRMATIONS
from raiden.utils.typing import BlockNumber
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_SERVICE_REGISTRY,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_libs.cli import blockchain_options, common_options, setup_sentry

log = structlog.get_logger(__name__)


@blockchain_options(
    contracts=[
        CONTRACT_TOKEN_NETWORK_REGISTRY,
        CONTRACT_USER_DEPOSIT,
        CONTRACT_MONITORING_SERVICE,
        CONTRACT_SERVICE_REGISTRY,
    ]
)
@click.command()
@click.option(
    "--min-reward",
    default=0,
    type=click.IntRange(min=0),
    help="Minimum reward which is required before processing requests",
)
@click.option(
    "--confirmations",
    default=DEFAULT_NUMBER_OF_BLOCK_CONFIRMATIONS,
    type=click.IntRange(min=0),
    help="Number of block confirmations to wait for",
)
@click.option(
    "--debug-shell",
    default=False,
    type=bool,
    help="Open a python shell with an initialized MonitoringService instance",
)
@common_options("raiden-monitoring-service")
def main(  # pylint: disable=too-many-arguments
    private_key: str,
    state_db: str,
    web3: Web3,
    contracts: Dict[str, Contract],
    start_block: BlockNumber,
    confirmations: BlockNumber,
    min_reward: int,
    debug_shell: bool,
) -> int:
    """ The Monitoring service for the Raiden Network. """
    log.info("Starting Raiden Monitoring Service")
    log.info("Web3 client", node_address=web3.providers[0].endpoint_uri)
    hex_addresses = {
        name: to_checksum_address(contract.address) for name, contract in contracts.items()
    }
    log.info("Contract information", addresses=hex_addresses, start_block=start_block)

    ms = MonitoringService(
        web3=web3,
        private_key=private_key,
        contracts=contracts,
        sync_start_block=start_block,
        required_confirmations=confirmations,
        db_filename=state_db,
        min_reward=min_reward,
    )

    if debug_shell:
        import IPython

        IPython.embed()
        return 0

    ms.start()

    return 0


if __name__ == "__main__":
    setup_sentry()
    main(auto_envvar_prefix="MS")
