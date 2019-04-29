import sys
import traceback
from typing import Any

import structlog
from gevent.hub import Hub

log = structlog.get_logger(__name__)
_original_error_handler = Hub.handle_error


def error_handler(_self: Any, _context: Any, etype: Any, value: Any, tb: Any) -> None:
    if issubclass(type, Hub.NOT_ERROR):
        return
    if issubclass(type, KeyboardInterrupt):
        log.info("Service termination requested by user.")
        sys.exit()

    log.critical(
        "Unhandled exception. Terminating the program..."
        "Please report this issue at "
        "https://github.com/raiden-network/raiden-services/issues"
    )
    traceback.print_exception(etype=etype, value=value, tb=tb)
    sys.exit(1)


def register_error_handler() -> None:
    """Sets the default error handler, overwriting the previous one"""
    Hub.handle_error = error_handler


def unregister_error_handler() -> None:
    """Resets the error handler to the original gevent handler"""
    Hub.handle_error = _original_error_handler
