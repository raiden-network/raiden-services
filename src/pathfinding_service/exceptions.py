from typing import Any, Dict, Optional


class ApiException(Exception):
    """An exception that can be returned via the REST API"""
    msg: str = 'Unknown Error'
    http_code: int = 400
    error_code: int = 0
    error_details: Optional[Dict[str, Any]] = None

    def __init__(self, msg=None, **details):
        if msg:
            self.msg = msg
        self.error_details = details

    def __str__(self):
        return f'{self.__class__.__name__}({self.error_details})'


class InvalidRequest(ApiException):
    """Request arguments failed schema validation"""
    error_code = 2000
    msg = 'Request parameter failed validation. See `error_details`.'


# ### BadIOU 21xx ###

class BadIOU(ApiException):
    error_code = 2100


class MissingIOU(BadIOU):
    error_code = 2101
    msg = 'No IOU for service fees has been provided'


class WrongIOURecipient(BadIOU):
    error_code = 2102
    msg = 'IOU not addressed to the correct receiver'


class IOUExpiredTooEarly(BadIOU):
    error_code = 2103
    msg = 'Please use a higher `expiration_block`'


class InvalidIOUSignature(BadIOU):
    error_code = 2104
    msg = 'The signature did not match the IOU content'


class InsufficientServicePayment(BadIOU):
    error_code = 2105
    msg = 'The provided payment is lower than service fee'


class IOUAlreadyClaimed(BadIOU):
    error_code = 2106
    msg = 'The IOU is already claimed. Please start new session with different `expiration_block`.'
