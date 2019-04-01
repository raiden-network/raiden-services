"""Console script for pathfinding_service."""
from gevent import monkey, config  # isort:skip # noqa
# there were some issues with the 'thread' resolver, remove it from the options
config.resolver = ['dnspython', 'ares', 'block'] # noqa
monkey.patch_all()  # isort:skip # noqa

import click
import structlog

from pathfinding_service import PathfindingService
from pathfinding_service.api.rest import ServiceApi
from pathfinding_service.config import DEFAULT_API_HOST, DEFAULT_POLL_INTERVALL
from raiden.utils.typing import BlockNumber
from raiden_contracts.constants import CONTRACT_TOKEN_NETWORK_REGISTRY, CONTRACT_USER_DEPOSIT
from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path
from raiden_libs.cli import blockchain_options, common_options, connect_to_blockchain
from raiden_libs.contract_info import START_BLOCK_ID
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
    web3, contract_infos = connect_to_blockchain(
        eth_rpc=eth_rpc,
        registry_address=registry_address,
        user_deposit_contract_address=user_deposit_contract_address,
        start_block=start_block,
        # necessary so that the overwrite logic works properly
        monitor_contract_address=Address('0x' + '1' * 40),
        contracts_version=contracts_version,
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
