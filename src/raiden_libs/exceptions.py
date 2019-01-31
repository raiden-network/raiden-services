class RaidenException(Exception):
    pass


class MessageFormatError(RaidenException):
    """Raised on unexpected data in the message"""
    pass


class MessageTypeError(RaidenException):
    """Raised on an unexpected message type"""
    pass


class InvalidSignature(RaidenException):
    """Raised on invalid signature recover/verify"""
    pass
