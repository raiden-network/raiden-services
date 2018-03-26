class RaidenException(Exception):
    pass


class MessageSignatureError(RaidenException):
    """Raised on message signature mismatch"""
    pass


class MessageFormatError(RaidenException):
    """Raised on unexpected data in the message"""
    pass
