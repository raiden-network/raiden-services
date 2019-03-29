import json
import os
from typing import Callable

import click
import structlog
from eth_account import Account

from raiden_libs.logging import setup_logging

log = structlog.get_logger(__name__)


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
