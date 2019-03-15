from typing import ClassVar, Optional, Type

import marshmallow
from dataclasses import dataclass, field
from eth_abi import encode_single
from eth_utils import decode_hex, encode_hex
from marshmallow_dataclass import add_schema
from web3 import Web3

from raiden.utils.typing import BlockNumber, Signature, TokenAmount
from raiden_libs.exceptions import InvalidSignature
from raiden_libs.types import Address
from raiden_libs.utils import eth_recover


class HexedBytes(marshmallow.fields.Field):
    """ Use `bytes` in the dataclass, serialize to hex encoding"""

    def _serialize(self, value, attr, obj):
        return encode_hex(value)

    def _deserialize(self, value, attr, data):
        return decode_hex(value)


@add_schema
@dataclass
class IOU:
    sender: Address
    receiver: Address
    amount: TokenAmount
    expiration_block: BlockNumber
    signature: Signature = field(metadata={"marshmallow_field": HexedBytes()})
    claimed: Optional[bool] = None
    Schema: ClassVar[Type[marshmallow.Schema]]

    def is_signature_valid(self):
        packed_data = (
            Web3.toBytes(hexstr=self.sender) +
            Web3.toBytes(hexstr=self.receiver) +
            encode_single('uint256', self.amount) +
            encode_single('uint256', self.expiration_block)
        )
        try:
            return eth_recover(packed_data, self.signature) == self.sender
        except InvalidSignature:
            return False
