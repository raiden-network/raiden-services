import json
import os
from typing import Callable

import click
import structlog
from eth_account import Account
from eth_utils import is_checksum_address

from raiden_libs.logging import setup_logging

log = structlog.get_logger(__name__)

DEFAULT_REQUIRED_CONFIRMATIONS = 8  # ~2min with 15s blocks


def _open_keystore(ctx: click.Context, param: click.Parameter, value: str) -> None:
    keystore_file = value
    password = ctx.params.pop('password')
    with open(keystore_file, 'r') as keystore:
        try:
            ctx.params['private_key'] = Account.decrypt(
                keyfile_json=json.load(keystore),
                password=password,
            ).hex()
        except ValueError as error:
            log.critical(
                'Could not decode keyfile with given password. Please try again.',
                reason=str(error),
            )
            ctx.exit(1)


def validate_address(ctx, param, value):
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
        for option in reversed([
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
        ]):
            func = option(func)  # type: ignore
        return func

    return decorator


def blockchain_options(func: Callable) -> Callable:
    """A decorator to be used with all service commands

    It will pass two new args to the given func:
    * private_key (as a result of `--keystore-file` and `--password`)
    * state_db

    The `app_name` will be used to determine the state_db location.
    """
    for option in reversed([
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
    ]):
        func = option(func)  # type: ignore

    return func
