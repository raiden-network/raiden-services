from gevent import monkey  # isort:skip # noqa

monkey.patch_all(subprocess=False, thread=False)  # isort:skip # noqa

import os.path
import sys
from typing import List

import click
import structlog

from monitoring_service.constants import MS_DISCLAIMER
from monitoring_service.database import SharedDatabase
from raiden.utils.cli import ChainChoiceType
from raiden_contracts.utils.type_aliases import PrivateKey
from raiden_libs.cli import common_options, setup_sentry
from raiden_libs.constants import CONFIRMATION_OF_UNDERSTANDING
from request_collector.server import RequestCollector

log = structlog.get_logger(__name__)


@click.command()
@click.option(
    "--chain-id",
    type=ChainChoiceType(["mainnet", "ropsten", "rinkeby", "goerli", "kovan", "<CHAIN_ID>"]),
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
        '"<CHAIN_ID>": use the given chain id directly\n'
    ),
)
@click.option(
    "--matrix-server",
    type=str,
    multiple=True,
    help="Use this matrix server instead of the default ones. Include protocol in argument.",
)
@click.option(
    "--accept-disclaimer",
    type=bool,
    default=False,
    help="Bypass the experimental software disclaimer prompt",
    is_flag=True,
)
@common_options("raiden-monitoring-service")
def main(
    private_key: PrivateKey, state_db: str, matrix_server: List[str], accept_disclaimer: bool
) -> int:
    """The request collector for the monitoring service."""
    log.info("Starting Raiden Monitoring Request Collector")
    click.secho(MS_DISCLAIMER, fg="yellow")
    if not accept_disclaimer:
        click.confirm(CONFIRMATION_OF_UNDERSTANDING, abort=True)
    if state_db != ":memory:" and not os.path.exists(state_db):
        log.error(
            "Database file from monitoring service not found. Is the monitoring service running?",
            expected_db_path=state_db,
        )
        sys.exit(1)

    database = SharedDatabase(state_db)

    service = RequestCollector(
        private_key=private_key, state_db=database, matrix_servers=matrix_server
    )

    service.start()
    service.listen_forever()

    print("Exiting...")
    return 0


if __name__ == "__main__":
    setup_sentry()
    main(auto_envvar_prefix="MSRC")  # pragma: no cover
