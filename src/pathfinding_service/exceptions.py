from typing import Any, Dict, Optional


class InvalidGlobalMessage(Exception):
    """A global message received via matrix is invalid and must be discarded"""


class InvalidCapacityUpdate(InvalidGlobalMessage):
    pass


class InvalidPFSFeeUpdate(InvalidGlobalMessage):
    pass


class UndefinedFee(Exception):
    """The fee schedule is not applicable resulting in undefined fees

    This should be handled by excluding the route from the results"""


class ApiException(Exception):
    """An exception that can be returned via the REST API"""

    msg: str = "Unknown Error"
    http_code: int = 400
    error_code: int = 0
    error_details: Optional[Dict[str, Any]] = None

    def __init__(self, msg: str = None, **details: Any):
        super(ApiException, self).__init__(msg)
        if msg:
            self.msg = msg
        self.error_details = details

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.error_details})"


# ### Generic Service Exceptions 20xx ###


class InvalidRequest(ApiException):
    """Request arguments failed schema validation"""

    error_code = 2000
    msg = "Request parameter failed validation. See `error_details`."


class InvalidSignature(ApiException):
    error_code = 2001
    msg = "The signature did not match the signed content."


class RequestOutdated(ApiException):
    error_code = 2002
    msg = "The request contains too old timestamps or nonces."


class InvalidTokenNetwork(ApiException):
    error_code = 2003
    msg = "Invalid token network."


class UnsupportedTokenNetwork(ApiException):
    error_code = 2004
    msg = "This service does not work on the given token network."


class UnsupportedChainID(ApiException):
    error_code = 2005
    msg = "This service does not work on the given blockchain."


# ### BadIOU 21xx ###


class BadIOU(ApiException):
    error_code = 2100


class MissingIOU(BadIOU):
    error_code = 2101
    msg = "No IOU for service fees has been provided."


class WrongIOURecipient(BadIOU):
    error_code = 2102
    msg = "IOU not addressed to the correct receiver."


class IOUExpiredTooEarly(BadIOU):
    error_code = 2103
    msg = "Please use a higher `expiration_block`."


class InsufficientServicePayment(BadIOU):
    error_code = 2104
    msg = "The provided payment is lower than service fee."


class IOUAlreadyClaimed(BadIOU):
    error_code = 2105
    msg = "The IOU is already claimed. Please start new session with different `expiration_block`."


class UseThisIOU(BadIOU):
    error_code = 2106
    msg = "Please increase the amount of the existing IOU instead of creating a new one."


class DepositTooLow(BadIOU):
    error_code = 2107
    msg = "Not enough deposit in UserDeposit contract."


class WrongOneToNAddress(BadIOU):
    error_code = 2108
    msg = "The IOU uses a different OneToN contract than the service"


# ### PFS specific errors 22xx ###


class NoRouteFound(ApiException):
    error_code = 2201
    http_code = 404
    msg = "No route between nodes found."
