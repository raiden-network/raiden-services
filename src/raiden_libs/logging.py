import logging
import sys
from dataclasses import asdict
from typing import Any, Dict

import structlog
from eth_utils import to_checksum_address, to_hex

from raiden.messages.abstract import Message
from raiden_libs.events import Event


def setup_logging(log_level: str) -> None:
    """ Basic structlog setup """

    logging.basicConfig(level=log_level, stream=sys.stdout, format="%(message)s")

    logging.getLogger("web3").setLevel("INFO")
    logging.getLogger("urllib3").setLevel("INFO")

    processors = [
        format_to_hex,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S.%f"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=processors + [structlog.dev.ConsoleRenderer()],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def make_bytes_readable(value: Any) -> Any:
    if isinstance(value, bytes):
        if len(value) == 20:
            return to_checksum_address(value)

        return to_hex(value)
    return value


def apply_recursive(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [apply_recursive(x) for x in value]
    if isinstance(value, dict):
        return {apply_recursive(k): apply_recursive(v) for k, v in value.items()}

    return make_bytes_readable(value)


def format_to_hex(_logger: Any, _log_method: Any, event_dict: Dict) -> Dict[str, Any]:
    for key, val in event_dict.items():
        if isinstance(val, (Event, Message)):
            name = val.__class__.__name__
            val = asdict(val)
            val["type_name"] = name

        event_dict[key] = apply_recursive(val)

    return event_dict
