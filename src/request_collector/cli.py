from gevent import monkey  # isort:skip # noqa

monkey.patch_all()  # isort:skip # noqa

import click
import structlog
from request_collector.server import RequestCollector

from monitoring_service.database import SharedDatabase
from raiden_libs.cli import common_options

log = structlog.get_logger(__name__)


@click.command()
@common_options('raiden-monitoring-service')
def main(private_key: str, state_db: str) -> int:
    """ The request collector for the monitoring service. """
    log.info("Starting Raiden Monitoring Request Collector")

    database = SharedDatabase(state_db)

    RequestCollector(private_key=private_key, state_db=database).listen_forever()

    print('Exiting...')
    return 0


if __name__ == "__main__":
    main(auto_envvar_prefix='MSRC')  # pragma: no cover
