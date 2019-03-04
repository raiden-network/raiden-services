class RaidenException(Exception):
    pass


class InvalidSignature(RaidenException):
    """Raised on invalid signature recover/verify"""
    pass
