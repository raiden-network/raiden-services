import json
import os
import sys
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple

import click
import structlog
from eth_account import Account
from eth_utils import is_checksum_address
from requests.exceptions import ConnectionError
from web3 import HTTPProvider, Web3
from web3.contract import Contract
from web3.middleware import geth_poa_middleware

from pathfinding_service.middleware import http_retry_with_backoff_middleware
from raiden.utils.typing import BlockNumber, ChainID
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_ONE_TO_N,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_libs.contract_info import CONTRACT_MANAGER, get_contract_addresses_and_start_block
from raiden_libs.logging import setup_logging
from raiden_libs.types import Address

log = structlog.get_logger(__name__)


def _open_keystore(keystore_file: str, password: str) -> str:
    with open(keystore_file, 'r') as keystore:
        try:
            private_key = Account.decrypt(
                keyfile_json=json.load(keystore), password=password
            ).hex()
            return private_key
        except ValueError as error:
            log.critical(
                'Could not decode keyfile with given password. Please try again.',
                reason=str(error),
            )
            sys.exit(1)


def validate_address(_ctx: click.Context, _param: click.Parameter, value: str) -> Optional[str]:
    if value is None:
        # None as default value allowed
        return None
    if not is_checksum_address(value):
        raise click.BadParameter('not an EIP-55 checksummed address')
    return value


def common_options(app_name: str) -> Callable:
    """A decorator to be used with all service commands

    It will pass new args to the given func:
    * private_key (as a result of `--keystore-file` and `--password`)
    * state_db
    * log_level

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
                ),
                click.password_option('--password', help='Password to unlock the keystore file.'),
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

        @wraps(func)
        def call_with_opened_keystore(**params: Any) -> Callable:
            params['private_key'] = _open_keystore(
                params.pop('keystore_file'), params.pop('password')
            )
            return func(**params)

        return call_with_opened_keystore

    return decorator


def blockchain_options(contracts: List[str], contracts_version: str = None) -> Callable:
    """A decorator providing blockchain related params to a command"""
    options = [
        click.Option(
            ['--eth-rpc'], default='http://localhost:8545', type=str, help='Ethereum node RPC URI'
        )
    ]

    arg_for_contract = {
        CONTRACT_TOKEN_NETWORK_REGISTRY: 'registry',
        CONTRACT_USER_DEPOSIT: 'user-deposit-contract',
        CONTRACT_MONITORING_SERVICE: 'monitor-contract',
        CONTRACT_ONE_TO_N: 'one-to-n-contract',
    }

    param_for_contract: Dict[str, str] = {}
    for c in contracts:
        option = click.Option(
            ['--{}-address'.format(arg_for_contract[c])],
            type=str,
            help=f'Address of the {c} contract',
            callback=validate_address,
        )
        options.append(option)
        param_for_contract[c] = option.human_readable_name

    def decorator(command: click.Command) -> click.Command:
        assert command.callback
        callback = command.callback

        command.params += options

        def call_with_blockchain_info(**params: Any) -> Callable:
            address_overwrites = {
                contract: params.pop(param) for contract, param in param_for_contract.items()
            }
            params['web3'], params['contracts'], params['start_block'] = connect_to_blockchain(
                eth_rpc=params.pop('eth_rpc'),
                used_contracts=contracts,
                address_overwrites=address_overwrites,
                contracts_version=contracts_version,
            )
            return callback(**params)

        command.callback = call_with_blockchain_info
        return command

    return decorator


def connect_to_blockchain(
    eth_rpc: str,
    used_contracts: List[str],
    address_overwrites: Dict[str, Address],
    contracts_version: str = None,
) -> Tuple[Web3, Dict[str, Contract], BlockNumber]:
    try:
        log.info('Starting Web3 client', node_address=eth_rpc)
        provider = HTTPProvider(eth_rpc)
        web3 = Web3(provider)
        # Will throw ConnectionError on bad Ethereum client
        chain_id = ChainID(int(web3.net.version))
    except ConnectionError:
        log.error(
            'Can not connect to the Ethereum client. Please check that it is running and that '
            'your settings are correct.',
            eth_rpc=eth_rpc,
        )
        sys.exit(1)

    # Add POA middleware for geth POA chains, no/op for other chains
    web3.middleware_stack.inject(geth_poa_middleware, layer=0)

    # give web3 some time between retries before failing
    provider.middlewares.replace('http_retry_request', http_retry_with_backoff_middleware)

    if contracts_version:
        log.info(f'Using contracts version: {contracts_version}')

    addresses, start_block = get_contract_addresses_and_start_block(
        chain_id=chain_id,
        contracts=used_contracts,
        address_overwrites=address_overwrites,
        contracts_version=contracts_version,
    )
    contracts = {
        c: web3.eth.contract(abi=CONTRACT_MANAGER.get_contract_abi(c), address=address)
        for c, address in addresses.items()
    }

    log.info('Contract information', addresses=addresses, start_block=start_block)
    return web3, contracts, start_block
