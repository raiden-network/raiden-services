import click
import structlog
from web3 import Web3

from monitoring_service.constants import DEFAULT_REQUIRED_CONFIRMATIONS
from monitoring_service.service import MonitoringService
from raiden.utils.typing import BlockNumber
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_libs.cli import blockchain_options, common_options
from raiden_libs.contract_info import START_BLOCK_ID

log = structlog.get_logger(__name__)


@blockchain_options(
    contracts=[CONTRACT_TOKEN_NETWORK_REGISTRY, CONTRACT_USER_DEPOSIT, CONTRACT_MONITORING_SERVICE]
)
@click.command()
@click.option(
    '--min-reward',
    default=0,
    type=click.IntRange(min=0),
    help='Minimum reward which is required before processing requests',
)
@click.option(
    '--confirmations',
    default=DEFAULT_REQUIRED_CONFIRMATIONS,
    type=click.IntRange(min=0),
    help='Number of block confirmations to wait for',
)
@common_options('raiden-monitoring-service')
def main(
    private_key: str,
    state_db: str,
    web3: Web3,
    contract_infos: dict,
    confirmations: BlockNumber,
    min_reward: int,
) -> int:
    """ The Monitoring service for the Raiden Network. """
    log.info("Starting Raiden Monitoring Service")

    ms = MonitoringService(
        web3=web3,
        private_key=private_key,
        registry_address=contract_infos[CONTRACT_TOKEN_NETWORK_REGISTRY],
        monitor_contract_address=contract_infos[CONTRACT_MONITORING_SERVICE],
        user_deposit_contract_address=contract_infos[CONTRACT_USER_DEPOSIT],
        sync_start_block=contract_infos[START_BLOCK_ID],
        required_confirmations=confirmations,
        db_filename=state_db,
        min_reward=min_reward,
    )
    ms.start()

    return 0


if __name__ == '__main__':
    main(auto_envvar_prefix='MS')
