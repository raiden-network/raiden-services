from eth_utils import is_checksum_address


class address_property(object):
    def __init__(self, private_attribute_name, default=0):
        self.private_attribute_name = private_attribute_name
        self.default = default

    def __get__(self, obj, typ):
        if not obj:
            return self
        return getattr(obj, self.private_attribute_name, self.default)

    def __set__(self, obj, value):
        if isinstance(value, str) is False:
            raise ValueError("%s requires a string" % (self.__class__.__name__))
        if is_checksum_address(value) is False:
            raise ValueError("%s requires a checksummed ethereum address" %
                             (self.__class__.__name__))
        setattr(obj, self.private_attribute_name, value)
