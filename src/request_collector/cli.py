from gevent import monkey  # isort:skip # noqa
monkey.patch_all()  # isort:skip # noqa

import json
import os
import sys

import click
import structlog
from eth_account import Account
from eth_utils import encode_hex, is_checksum_address
from request_collector.server import RequestCollector

from monitoring_service.database import SharedDatabase
from raiden_libs.logging import setup_logging

log = structlog.get_logger(__name__)


def validate_address(ctx, param, value):
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
    '--state-db',
    default=os.path.join(click.get_app_dir('raiden-monitoring-service'), 'state.db'),
    type=str,
    help='State DB to save received balance proofs to.',
)
@click.option(
    '--log-level',
    default='INFO',
    type=click.Choice(['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']),
    help='Print log messages of this level and more important ones',
)
def main(
    keystore_file: str,
    password: str,
    state_db: str,
    log_level: str,
):
    """Console script for request_collector.

    Logging can be quickly set by specifying a global log level or in a
    detailed way by using a log configuration file. See
    https://docs.python.org/3.7/library/logging.config.html#logging-config-dictschema
    for a detailed description of the format.
    """
    setup_logging(log_level)

    with open(keystore_file, 'r') as keystore:
        try:
            private_key = Account.decrypt(
                keyfile_json=json.load(keystore),
                password=password,
            )
        except ValueError:
            log.critical('Could not decode keyfile with given password. Please try again.')
            sys.exit(1)

    log.info("Starting Raiden Monitoring Request Collector")

    database = SharedDatabase(state_db)

    RequestCollector(
        private_key=encode_hex(private_key),
        state_db=database,
    ).listen_forever()

    print('Exiting...')
    return 0


if __name__ == "__main__":
    main(auto_envvar_prefix='MSRC')  # pragma: no cover
