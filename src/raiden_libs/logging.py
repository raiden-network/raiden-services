import logging
import sys

import structlog


def setup_logging(log_level: str) -> None:
    """ Basic structlog setup """

    logging.basicConfig(level=log_level, stream=sys.stdout, format="%(message)s")

    logging.getLogger('web3').setLevel('INFO')
    logging.getLogger('urllib3').setLevel('INFO')
    # don't show urllib3.connectionpoool errors
    logging.getLogger('urllib3.connectionpool').setLevel('ERROR')

    chain = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S.%f"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(),
    ]
    structlog.configure_once(
        processors=chain,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
