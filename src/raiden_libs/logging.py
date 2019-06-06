import logging
import sys
from dataclasses import asdict
from typing import Any, Dict

import structlog
from eth_utils import to_checksum_address, to_hex

from raiden_libs.events import Event


def setup_logging(log_level: str) -> None:
    """ Basic structlog setup """

    logging.basicConfig(level=log_level, stream=sys.stdout, format="%(message)s")

    logging.getLogger("web3").setLevel("INFO")
    logging.getLogger("urllib3").setLevel("INFO")

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S.%f"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def log_event(event: Event) -> Dict[str, Any]:
    event_data = asdict(event)

    for key, val in event_data.items():
        if isinstance(val, bytes):
            if len(val) == 20:
                event_data[key] = to_checksum_address(val)
            else:
                event_data[key] = to_hex(val)

    return event_data
