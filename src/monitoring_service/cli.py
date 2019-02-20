import json
import os
import sys
from typing import Any, Optional

import click
import structlog
from eth_account import Account
from eth_utils import is_checksum_address
from web3 import HTTPProvider, Web3

from monitoring_service.constants import DEFAULT_REQUIRED_CONFIRMATIONS
from monitoring_service.service import MonitoringService
from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path
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
    required=True,
    help='Address of the token network registry',
    callback=validate_address,
)
@click.option(
    '--monitor-contract-address',
    type=str,
    required=True,
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
def main(
    keystore_file: str,
    password: str,
    eth_rpc: str,
    registry_address: Address,
    monitor_contract_address: Address,
    start_block: int,
    confirmations: int,
    log_level: str,
    state_db: str,
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
    contract_manager = ContractManager(contracts_precompiled_path())

    ms = MonitoringService(
        web3=web3,
        contract_manager=contract_manager,
        private_key=private_key,
        registry_address=registry_address,
        monitor_contract_address=monitor_contract_address,
        sync_start_block=start_block,
        required_confirmations=confirmations,
        db_filename=state_db,
    )
    ms.start()


if __name__ == '__main__':
    main(auto_envvar_prefix='MS')
