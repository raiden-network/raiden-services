from typing import ClassVar, Type

import marshmallow
from eth_abi import encode_single
from eth_utils import decode_hex
from marshmallow_dataclass import dataclass
from web3 import Web3

from raiden_libs.exceptions import InvalidSignature
from raiden_libs.utils import eth_recover

# from raiden_libs.types import Address
# from raiden.utils.typing import (
#     BlockNumber,
#     Signature,
#     TokenAmount,
# )


# @dataclass
# class IOU:
#     sender: Address
#     receiver: Address
#     amount: TokenAmount
#     expiration_block: BlockNumber
#     signature: Signature
#     Schema: ClassVar[Type[marshmallow.Schema]]

#     def is_signature_valid(self):
#         packed_data = (
#             Web3.toBytes(hexstr=self.sender) +
#             Web3.toBytes(hexstr=self.receiver) +
#             encode_single('uint256', self.amount) +
#             encode_single('uint256', self.expiration_block)
#         )
#         try:
#             return eth_recover(packed_data, decode_hex(self.signature)) == self.sender
#         except InvalidSignature:
#             return False


@dataclass
class IOU:
    sender: str
    receiver: str
    amount: int
    expiration_block: int
    signature: str
    Schema: ClassVar[Type[marshmallow.Schema]]

    def is_signature_valid(self):
        packed_data = (
            Web3.toBytes(hexstr=self.sender) +
            Web3.toBytes(hexstr=self.receiver) +
            encode_single('uint256', self.amount) +
            encode_single('uint256', self.expiration_block)
        )
        try:
            return eth_recover(packed_data, decode_hex(self.signature)) == self.sender
        except InvalidSignature:
            return False
