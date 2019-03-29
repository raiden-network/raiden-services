import sys

import click
import structlog
from web3 import HTTPProvider, Web3
from web3.middleware import geth_poa_middleware

from monitoring_service.constants import DEFAULT_REQUIRED_CONFIRMATIONS
from monitoring_service.service import MonitoringService
from raiden.utils.typing import BlockNumber, ChainID
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path
from raiden_libs.cli import blockchain_options, common_options, validate_address
from raiden_libs.contract_info import START_BLOCK_ID, get_contract_addresses_and_start_block
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
    confirmations: int,
    monitor_contract_address: Address,
    min_reward: int,
) -> None:
    provider = HTTPProvider(eth_rpc)
    web3 = Web3(provider)

    # Add POA middleware for geth POA chains, no/op for other chains
    web3.middleware_stack.inject(geth_poa_middleware, layer=0)

    contract_manager = ContractManager(contracts_precompiled_path())
    contract_infos = get_contract_addresses_and_start_block(
        chain_id=ChainID(int(web3.net.version)),
        contracts_version=None,
        token_network_registry_address=registry_address,
        monitor_contract_address=monitor_contract_address,
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
            monitor_contract_address=contract_infos[CONTRACT_MONITORING_SERVICE],
            user_deposit_contract_address=contract_infos[CONTRACT_USER_DEPOSIT],
            sync_start_block=contract_infos[START_BLOCK_ID],
        )

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
