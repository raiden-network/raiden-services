import logging
import sys
from dataclasses import asdict
from typing import Any, Dict

import structlog
from eth_utils import to_checksum_address, to_hex

from raiden.messages import Message
from raiden_libs.events import Event


def setup_logging(log_level: str) -> None:
    """ Basic structlog setup """

    logging.basicConfig(level=log_level, stream=sys.stdout, format="%(message)s")

    logging.getLogger("web3").setLevel("INFO")
    logging.getLogger("urllib3").setLevel("INFO")

    structlog.configure(
        processors=[
            format_to_hex,
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


def change_bytes(event_dict: Dict, key: Any, val: bytes) -> Dict[str, Any]:
    if len(val) == 20:
        event_dict[key] = to_checksum_address(val)
    else:
        event_dict[key] = to_hex(val)
    return event_dict


def format_to_hex(_logger: Any, _log_method: Any, event_dict: Dict) -> Dict[str, Any]:
    for key, val in event_dict.items():
        if isinstance(val, bytes):
            change_bytes(event_dict, key, val)
        if isinstance(val, (Event, Message)):
            event_data = asdict(val)
            for keys, value in event_data.items():
                if isinstance(value, bytes):
                    change_bytes(event_data, keys, value)
            event_dict[key] = event_data
            event_dict[key]["event_name"] = val.__class__.__name__
    return event_dict
