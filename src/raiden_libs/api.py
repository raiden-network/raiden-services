import structlog
from flask import Response
from flask_restful import Api

from raiden_libs.exceptions import ApiException

log = structlog.get_logger(__name__)


class ApiWithErrorHandler(Api):
    def handle_error(self, e: Exception) -> Response:
        if isinstance(e, ApiException):
            log.warning(
                "Error while handling request", error=e, details=e.error_details, message=e.msg
            )
            return self.make_response(
                {"errors": e.msg, "error_code": e.error_code, "error_details": e.error_details},
                e.http_code,
            )
        return super().handle_error(e)
