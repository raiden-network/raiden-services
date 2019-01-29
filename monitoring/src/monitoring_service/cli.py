import click
import structlog
from eth_utils import is_checksum_address
from web3 import HTTPProvider, Web3

from monitoring_service.constants import DEFAULT_REQUIRED_CONFIRMATIONS
from monitoring_service.service import MonitoringService
from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path
from raiden_libs.types import Address

log = structlog.get_logger(__name__)


def validate_address(_ctx, _param, value):
    if value is None:
        # None as default value allowed
        return None
    if not is_checksum_address(value):
        raise click.BadParameter('not an EIP-55 checksummed address')
    return value


@click.command()
@click.option(
    '--private-key',
    default=None,
    required=True,
    help='Private key to use (the address should have enough ETH balance to send transactions)',
)
@click.option(
    '--eth-rpc',
    default='http://parity.ropsten.ethnodes.brainbot.com:8545',
    type=str,
    help='Ethereum node RPC URI',
)
@click.option(
    '--registry-address',
    type=str,
    help='Address of the token network registry',
    default='0x40a5D15fD98b9a351855D64daa9bc621F400cbc5',
    callback=validate_address,
)
@click.option(
    '--monitor-contract-address',
    type=str,
    help='Address of the token monitor contract',
    default='0x1111111111111111111111111111111111111111',
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
def main(
    private_key: str,
    eth_rpc: str,
    registry_address: Address,
    monitor_contract_address: Address,
    start_block: int,
    confirmations: int,
):
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
    )

    ms.start()


if __name__ == '__main__':
    main(auto_envvar_prefix='MS')
