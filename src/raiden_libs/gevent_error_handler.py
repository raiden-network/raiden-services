from typing import Any, Callable

from gevent.hub import Hub

IGNORE_ERROR = Hub.SYSTEM_ERROR + Hub.NOT_ERROR

_original_error_handler = Hub.handle_error


def register_error_handler(error_handler: Callable) -> None:
    """Sets the current error handler, overwriting the previous ones"""

    def custom_handle_error(self: Any, context: Any, type: Any, value: Any, tb: Any) -> None:
        if not issubclass(type, IGNORE_ERROR):
            error_handler(context, (type, value, tb))

    Hub.handle_error = custom_handle_error


def unregister_error_handler() -> None:
    """Resets the error handler to the original gevent handler"""
    Hub.handle_error = _original_error_handler
