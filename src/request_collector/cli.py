from gevent import monkey  # isort:skip # noqa

monkey.patch_all(subprocess=False, thread=False)  # isort:skip # noqa

import os.path
import sys

import click
import structlog
from request_collector.server import RequestCollector

from monitoring_service.database import SharedDatabase
from raiden.utils.cli import NetworkChoiceType
from raiden_libs.cli import common_options, setup_sentry

log = structlog.get_logger(__name__)


@click.command()
@click.option(
    "--chain-id",
    type=NetworkChoiceType(["mainnet", "ropsten", "rinkeby", "goerli", "kovan", "<NETWORK_ID>"]),
    required=True,
    show_default=True,
    help=(
        "Specify the chain name/id of the Ethereum network to run Raiden on.\n"
        "Available networks:\n"
        '"mainnet" - network id: 1\n'
        '"ropsten" - network id: 3\n'
        '"rinkeby" - network id: 4\n'
        '"goerli" - network id: 5\n'
        '"kovan" - network id: 42\n'
        '"<NETWORK_ID>": use the given network id directly\n'
    ),
)
@common_options("raiden-monitoring-service")
def main(private_key: str, state_db: str) -> int:
    """ The request collector for the monitoring service. """
    log.info("Starting Raiden Monitoring Request Collector")

    if state_db != ":memory:" and not os.path.exists(state_db):
        log.error(
            "Database file from monitoring service not found. Is the monitoring service running?",
            expected_db_path=state_db,
        )
        sys.exit(1)

    database = SharedDatabase(state_db)

    service = RequestCollector(private_key=private_key, state_db=database)

    service.start()
    service.listen_forever()

    print("Exiting...")
    return 0


if __name__ == "__main__":
    setup_sentry()
    main(auto_envvar_prefix="MSRC")  # pragma: no cover
