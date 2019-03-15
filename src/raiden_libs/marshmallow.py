import marshmallow
from eth_utils import decode_hex, encode_hex


class HexedBytes(marshmallow.fields.Field):
    """ Use `bytes` in the dataclass, serialize to hex encoding"""

    def _serialize(self, value, attr, obj):
        return encode_hex(value)

    def _deserialize(self, value, attr, data):
        return decode_hex(value)
