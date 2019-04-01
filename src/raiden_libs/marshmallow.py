from typing import Any

import marshmallow
from eth_utils import decode_hex, encode_hex


class HexedBytes(marshmallow.fields.Field):
    """ Use `bytes` in the dataclass, serialize to hex encoding"""

    def _serialize(self, value: bytes, attr: Any, obj: Any) -> str:
        return encode_hex(value)

    def _deserialize(self, value: str, attr: Any, data: Any) -> bytes:
        return decode_hex(value)
