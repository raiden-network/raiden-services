import json
import os
import sys
from typing import Any, Optional

import click
import structlog
from eth_account import Account
from eth_utils import is_checksum_address
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
from raiden_libs.contract_info import START_BLOCK_ID, get_contract_addresses_and_start_block
from raiden_libs.logging import setup_logging
from raiden_libs.types import Address

log = structlog.get_logger(__name__)


def validate_address(_ctx: Any, _param: Any, value: Optional[str]) -> Optional[str]:
    if value is None:
        # None as default value allowed
        return None
    if not is_checksum_address(value):
        raise click.BadParameter('not an EIP-55 checksummed address')
    return value


@click.command()
@click.option(
    '--keystore-file',
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help='Path to a keystore file.',
)
@click.password_option(
    '--password',
    help='Password to unlock the keystore file.',
)
@click.option(
    '--eth-rpc',
    default='http://parity.ropsten.ethnodes.brainbot.com:8545',
    type=str,
    help='Ethereum node RPC URI.',
)
@click.option(
    '--registry-address',
    type=str,
    help='Address of the token network registry',
    callback=validate_address,
)
@click.option(
    '--monitor-contract-address',
    type=str,
    help='Address of the token monitor contract',
    callback=validate_address,
)
@click.option(
    '--user-deposit-contract-address',
    type=str,
    help='Address of the token monitor contract',
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
    '--log-level',
    default='INFO',
    type=click.Choice(['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']),
    help='Print log messages of this level and more important ones',
)
@click.option(
    '--state-db',
    default=os.path.join(click.get_app_dir('raiden-monitoring-service'), 'state.db'),
    type=str,
    help='Path to SQLite3 db which stores the application state',
)
@click.option(
    '--min-reward',
    default=0,
    type=click.IntRange(min=0),
    help='Minimum reward which is required before processing requests',
)
def main(
    keystore_file: str,
    password: str,
    eth_rpc: str,
    registry_address: Address,
    monitor_contract_address: Address,
    user_deposit_contract_address: Address,
    start_block: BlockNumber,
    confirmations: int,
    log_level: str,
    state_db: str,
    min_reward: int,
) -> None:
    setup_logging(log_level)

    with open(keystore_file, 'r') as keystore:
        try:
            private_key = Account.decrypt(
                keyfile_json=json.load(keystore),
                password=password,
            )
        except ValueError as error:
            log.critical(
                'Could not decode keyfile with given password. Please try again.',
                reason=str(error),
            )
            sys.exit(1)

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
