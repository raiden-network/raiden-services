import json
import os
import sys
from typing import Callable, Tuple

import click
import structlog
from eth_account import Account
from eth_utils import is_checksum_address
from web3 import HTTPProvider, Web3
from web3.middleware import geth_poa_middleware
from requests.exceptions import ConnectionError

from pathfinding_service.middleware import http_retry_with_backoff_middleware
from raiden.utils.typing import BlockNumber, ChainID
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_libs.contract_info import START_BLOCK_ID, get_contract_addresses_and_start_block
from raiden_libs.logging import setup_logging
from raiden_libs.types import Address

log = structlog.get_logger(__name__)

DEFAULT_REQUIRED_CONFIRMATIONS = 8  # ~2min with 15s blocks


def _open_keystore(ctx: click.Context, param: click.Parameter, value: str) -> None:
    keystore_file = value
    password = ctx.params.pop('password')
    with open(keystore_file, 'r') as keystore:
        try:
            ctx.params['private_key'] = Account.decrypt(
                keyfile_json=json.load(keystore), password=password
            ).hex()
        except ValueError as error:
            log.critical(
                'Could not decode keyfile with given password. Please try again.',
                reason=str(error),
            )
            ctx.exit(1)


def validate_address(ctx: click.Context, param: click.Parameter, value: str) -> str:
    if value is None:
        # None as default value allowed
        return None
    if not is_checksum_address(value):
        raise click.BadParameter('not an EIP-55 checksummed address')
    return value


def common_options(app_name: str) -> Callable:
    """A decorator to be used with all service commands

    It will pass two new args to the given func:
    * private_key (as a result of `--keystore-file` and `--password`)
    * state_db

    The `app_name` will be used to determine the state_db location.
    """

    def decorator(func: Callable) -> Callable:
        for option in reversed(
            [
                click.option(
                    '--keystore-file',
                    required=True,
                    type=click.Path(exists=True, dir_okay=False, readable=True),
                    help='Path to a keystore file.',
                    callback=_open_keystore,
                    expose_value=False,  # only the private_key is used
                ),
                click.password_option(
                    '--password',
                    help='Password to unlock the keystore file.',
                    is_eager=True,  # read the password before opening keystore
                ),
                click.option(
                    '--state-db',
                    default=os.path.join(click.get_app_dir(app_name), 'state.db'),
                    type=str,
                    help='Path to SQLite3 db which stores the application state',
                ),
                click.option(
                    '--log-level',
                    default='INFO',
                    type=click.Choice(['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']),
                    help='Print log messages of this level and more important ones',
                    callback=lambda ctx, param, value: setup_logging(str(value)),
                    expose_value=False,
                ),
            ]
        ):
            func = option(func)
        return func

    return decorator


def blockchain_options(func: Callable) -> Callable:
    """A decorator providing blockchain related params to a command"""
    for option in reversed(
        [
            click.option(
                '--eth-rpc',
                default='http://localhost:8545',
                type=str,
                help='Ethereum node RPC URI',
            ),
            click.option(
                '--registry-address',
                type=str,
                help='Address of the token network registry',
                callback=validate_address,
            ),
            click.option(
                '--user-deposit-contract-address',
                type=str,
                help='Address of the token monitor contract',
                callback=validate_address,
            ),
            click.option(
                '--start-block',
                default=0,
                type=click.IntRange(min=0),
                help='Block to start syncing at',
            ),
            click.option(
                '--confirmations',
                default=DEFAULT_REQUIRED_CONFIRMATIONS,
                type=click.IntRange(min=0),
                help='Number of block confirmations to wait for',
            ),
        ]
    ):
        func = option(func)

    return func


def connect_to_blockchain(
    eth_rpc: str,
    registry_address: Address,
    user_deposit_contract_address: Address,
    start_block: BlockNumber,
    monitor_contract_address: Address,
    contracts_version: str = None,
) -> Tuple[Web3, dict]:
    try:
        log.info('Starting Web3 client', node_address=eth_rpc)
        provider = HTTPProvider(eth_rpc)
        web3 = Web3(provider)
        # Will throw ConnectionError on bad Ethereum client
        chain_id = ChainID(int(web3.net.version))
    except ConnectionError:
        log.error(
            'Can not connect to the Ethereum client. Please check that it is running and that '
            'your settings are correct.'
        )
        sys.exit(1)

    # Add POA middleware for geth POA chains, no/op for other chains
    web3.middleware_stack.inject(geth_poa_middleware, layer=0)

    # give web3 some time between retries before failing
    provider.middlewares.replace('http_retry_request', http_retry_with_backoff_middleware)

    if contracts_version:
        log.info(f'Using contracts version: {contracts_version}')

    contract_infos = get_contract_addresses_and_start_block(
        chain_id=chain_id,
        contracts_version=contracts_version,
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
    return web3, contract_infos
