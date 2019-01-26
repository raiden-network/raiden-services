from gevent import monkey  # isort:skip # noqa
monkey.patch_all()  # isort:skip # noqa

import json
import logging
import logging.config
import os
from typing import TextIO

import click
from eth_utils import is_checksum_address
from old.state_db import StateDBSqlite
from request_collector.server import RequestCollector

from raiden_libs.transport import MatrixTransport

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
    '--monitoring-channel',
    default='#monitor_test:transport01.raiden.network',
    help='Location of the monitoring channel to connect to',
)
@click.option(
    '--matrix-homeserver',
    default='https://transport01.raiden.network',
    help='Matrix username',
)
@click.option(
    '--matrix-username',
    default=None,
    required=True,
    help='Matrix username',
)
@click.option(
    '--matrix-password',
    default=None,
    required=True,
    help='Matrix password',
)
@click.option(
    '--state-db',
    default=os.path.join(click.get_app_dir('raiden-monitoring-service'), 'state.db'),
    type=str,
    help='state DB to save received balance proofs to',
)
@click.option(
    '--log-level',
    default='INFO',
    type=click.Choice(['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']),
    help='Print log messages of this level and more important ones',
)
@click.option(
    '--log-config',
    type=click.File('r'),
    help='Use the given JSON file for logging configuration',
)
def main(
    monitoring_channel: str,
    matrix_homeserver: str,
    matrix_username: str,
    matrix_password: str,
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

    log.info("Starting Raiden Monitoring Request Collector")

    transport = MatrixTransport(
        matrix_homeserver,
        matrix_username,
        matrix_password,
        monitoring_channel,
    )

    database = StateDBSqlite(state_db)

    service = None
    try:
        service = RequestCollector(
            state_db=database,
            transport=transport,
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
