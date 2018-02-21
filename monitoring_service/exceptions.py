class MonitoringServiceException(Exception):
    pass


class MessageSignatureError(MonitoringServiceException):
    """Raised on message signature mismatch"""
    pass


class MessageFormatError(MonitoringServiceException):
    """Raised on unexpected data in the message"""
    pass
