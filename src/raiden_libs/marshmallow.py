from typing import Any

import marshmallow
from eth_utils import decode_hex, encode_hex, is_checksum_address, to_checksum_address


class HexedBytes(marshmallow.fields.Field):
    """ Use `bytes` in the dataclass, serialize to hex encoding"""

    def _serialize(self, value: bytes, attr: Any, obj: Any, **kwargs: Any) -> str:
        return encode_hex(value)

    def _deserialize(self, value: str, attr: Any, data: Any, **kwargs: Any) -> bytes:
        return decode_hex(value)


class ChecksumAddress(marshmallow.fields.Field):
    """ Use `bytes` in the dataclass, serialize to checksum address"""

    def _serialize(self, value: bytes, attr: Any, obj: Any, **kwargs: Any) -> str:
        return to_checksum_address(value)

    def _deserialize(self, value: str, attr: Any, data: Any, **kwargs: Any) -> bytes:
        if not is_checksum_address(value):
            raise marshmallow.ValidationError(f"Not a checksummed address: {value}")
        return decode_hex(value)
