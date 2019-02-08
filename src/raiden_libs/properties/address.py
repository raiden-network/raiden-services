from typing import Any

from eth_utils import is_checksum_address

from raiden_libs.types import Address


class address_property(object):
    def __init__(self, private_attribute_name: str, default: int = 0):
        self.private_attribute_name = private_attribute_name
        self.default = default

    def __get__(self, obj: str, typ: Any) -> Any:
        if not obj:
            return self
        return getattr(obj, self.private_attribute_name, self.default)

    def __set__(self, obj: str, value: Any) -> None:
        if not isinstance(value, str):
            raise ValueError("%s requires a string" % (self.__class__.__name__))
        if not is_checksum_address(value):
            raise ValueError("%s requires a checksummed ethereum address" %
                             (self.__class__.__name__))
        setattr(obj, self.private_attribute_name, Address(value))
