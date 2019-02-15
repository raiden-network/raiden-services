from gevent import monkey  # isort:skip # noqa
monkey.patch_all()  # isort:skip # noqa

import json
import logging
import logging.config
import os
import sys
from typing import TextIO

import click
from eth_account import Account
from eth_utils import encode_hex, is_checksum_address
from request_collector.server import RequestCollector

from monitoring_service.database import SharedDatabase

log = logging.getLogger(__name__)


def validate_address(ctx, param, value):
    if value is None:
        # None as default value allowed
        return None
    if not is_checksum_address(value):
        raise click.BadParameter('not an EIP-55 checksummed address')
    return value


def setup_logging(log_level: str, log_config: TextIO):
    """ Set log level and (optionally) detailed JSON logging config """
    # import pdb; pdb.set_trace()
    level = getattr(logging, log_level)
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%m-%d %H:%M:%S',
    )

    if log_config:
        config = json.load(log_config)
        logging.config.dictConfig(config)


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
    help='Print log messages of this level and more important ones.',
)
@click.option(
    '--log-config',
    type=click.File('r'),
    help='Use the given JSON file for logging configuration.',
)
def main(
    keystore_file: str,
    password: str,
    state_db: str,
    log_level: str,
    log_config: TextIO,
):
    """Console script for request_collector.

    Logging can be quickly set by specifying a global log level or in a
    detailed way by using a log configuration file. See
    https://docs.python.org/3.7/library/logging.config.html#logging-config-dictschema
    for a detailed description of the format.
    """
    assert log_config is None
    setup_logging(log_level, log_config)

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

    service = None
    try:
        service = RequestCollector(
            private_key=encode_hex(private_key),
            state_db=database,
        )

        service.run()
    except (KeyboardInterrupt, SystemExit):
        print('Exiting...')
    finally:
        log.info('Stopping Pathfinding Service...')
        if service:
            service.stop()

    return 0


if __name__ == "__main__":
    main(auto_envvar_prefix='MSRC')  # pragma: no cover
