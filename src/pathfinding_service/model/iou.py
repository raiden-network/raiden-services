from dataclasses import dataclass, field
from typing import ClassVar, Optional, Type

import marshmallow
from eth_abi import encode_single
from eth_utils import encode_hex, is_same_address, keccak
from marshmallow_dataclass import add_schema

from raiden.exceptions import InvalidSignature
from raiden.utils.signer import recover
from raiden.utils.typing import Address, BlockNumber, ChainID, Signature, TokenAmount
from raiden_contracts.constants import MessageTypeId
from raiden_libs.marshmallow import ChecksumAddress, HexedBytes


@add_schema
@dataclass
class IOU:
    sender: Address = field(metadata={"marshmallow_field": ChecksumAddress()})
    receiver: Address = field(metadata={"marshmallow_field": ChecksumAddress()})
    amount: TokenAmount
    expiration_block: BlockNumber
    one_to_n_address: Address = field(metadata={"marshmallow_field": ChecksumAddress()})
    chain_id: ChainID
    signature: Signature = field(metadata={"marshmallow_field": HexedBytes()})
    claimed: Optional[bool] = None
    Schema: ClassVar[Type[marshmallow.Schema]]

    def packed_data(self) -> bytes:
        return (
            self.one_to_n_address
            + encode_single("uint256", self.chain_id)
            + encode_single("uint256", MessageTypeId.IOU)
            + self.sender
            + self.receiver
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
    def session_id(self) -> str:
        """Session ID as used for OneToN.settled_sessions"""
        return encode_hex(
            keccak(self.receiver + self.sender + encode_single("uint256", self.expiration_block))
        )
