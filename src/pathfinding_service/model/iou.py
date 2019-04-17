from dataclasses import dataclass, field
from typing import ClassVar, Optional, Type

import marshmallow
from eth_abi import encode_single
from eth_utils import encode_hex, is_same_address, keccak
from marshmallow_dataclass import add_schema
from web3 import Web3

from raiden.exceptions import InvalidSignature
from raiden.utils.signer import recover
from raiden.utils.typing import BlockNumber, Signature, TokenAmount
from raiden_libs.marshmallow import HexedBytes
from raiden_libs.types import Address


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

    def packed_data(self) -> bytes:
        return (
            Web3.toBytes(hexstr=self.sender)
            + Web3.toBytes(hexstr=self.receiver)
            + encode_single("uint256", self.amount)
            + encode_single("uint256", self.expiration_block)
        )

    def is_signature_valid(self) -> bool:
        try:
            recovered_address = recover(self.packed_data(), self.signature)
        except InvalidSignature:
            return False
        return is_same_address(recovered_address, self.sender)

    @property
    def session_id(self) -> bytes:
        """Session ID as used for OneToN.settled_sessions"""
        return encode_hex(
            keccak(
                Web3.toBytes(hexstr=self.receiver)
                + Web3.toBytes(hexstr=self.sender)
                + encode_single("uint256", self.expiration_block)
            )
        )
