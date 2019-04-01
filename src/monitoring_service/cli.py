import click
import structlog

from monitoring_service.constants import DEFAULT_REQUIRED_CONFIRMATIONS
from monitoring_service.service import MonitoringService
from raiden.utils.typing import BlockNumber
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path
from raiden_libs.cli import (
    blockchain_options,
    common_options,
    connect_to_blockchain,
    validate_address,
)
from raiden_libs.contract_info import START_BLOCK_ID
from raiden_libs.types import Address

log = structlog.get_logger(__name__)


CONTEXT_SETTINGS = dict(
    default_map={'main': {
        'confirmations': DEFAULT_REQUIRED_CONFIRMATIONS,
    }},
)


@click.command(context_settings=CONTEXT_SETTINGS)
@click.option(
    '--monitor-contract-address',
    type=str,
    help='Address of the token monitor contract',
    callback=validate_address,
)
@click.option(
    '--min-reward',
    default=0,
    type=click.IntRange(min=0),
    help='Minimum reward which is required before processing requests',
)
@common_options('raiden-monitoring-service')
@blockchain_options
def main(
    private_key: str,
    state_db: str,

    eth_rpc: str,
    registry_address: Address,
    user_deposit_contract_address: Address,
    start_block: BlockNumber,
    monitor_contract_address: Address,

    min_reward: int,
    confirmations: int,
) -> None:
    web3, contract_infos = connect_to_blockchain(
        eth_rpc=eth_rpc,
        registry_address=registry_address,
        user_deposit_contract_address=user_deposit_contract_address,
        start_block=start_block,
        monitor_contract_address=monitor_contract_address,
    )
    contract_manager = ContractManager(contracts_precompiled_path())

    ms = MonitoringService(
        web3=web3,
        contract_manager=contract_manager,
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


if __name__ == '__main__':
    main(auto_envvar_prefix='MS')
