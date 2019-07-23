import sys
from typing import Any

import structlog
from gevent.hub import Hub

log = structlog.get_logger(__name__)
ORIGINAL_ERROR_HANDLER = Hub.handle_error


def error_handler(self: Any, _context: Any, etype: Any, value: Any, _tb: Any) -> None:
    if issubclass(etype, Hub.NOT_ERROR):
        return
    if issubclass(etype, KeyboardInterrupt):
        log.info("Service termination requested by user.")
        sys.exit()

    log.critical(
        "Unhandled exception. Terminating the program..."
        "Please report this issue at "
        "https://github.com/raiden-network/raiden-services/issues"
    )
    # This will properly raise the exception and stop the process
    Hub.handle_system_error(self, etype, value)


def register_error_handler() -> None:
    """Sets the default error handler, overwriting the previous one"""
    Hub.handle_error = error_handler


def unregister_error_handler() -> None:
    """Resets the error handler to the original gevent handler"""
    Hub.handle_error = ORIGINAL_ERROR_HANDLER
