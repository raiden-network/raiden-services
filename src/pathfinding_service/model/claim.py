from dataclasses import dataclass, field
from typing import ClassVar, Type

import marshmallow
from eth_abi import encode_single
from eth_typing import Address
from eth_utils import keccak
from marshmallow_dataclass import add_schema

from raiden.utils.signer import recover
from raiden_contracts.utils.type_aliases import ChainID, ChannelID, Signature, TokenAmount
from raiden_libs.marshmallow import ChecksumAddress, HexedBytes


@add_schema
@dataclass
class Claim:
    chain_id: ChainID
    token_network_address: Address = field(metadata={"marshmallow_field": ChecksumAddress()})
    owner: Address = field(metadata={"marshmallow_field": ChecksumAddress()})
    partner: Address = field(metadata={"marshmallow_field": ChecksumAddress()})
    total_amount: TokenAmount
    signature: Signature = field(metadata={"marshmallow_field": HexedBytes()})
    Schema: ClassVar[Type[marshmallow.Schema]]

    def packed_data(self) -> bytes:
        return (
            self.token_network_address
            + encode_single("uint256", self.chain_id)
            + self.owner
            + self.partner
            + encode_single("uint256", self.total_amount)
        )

    def signer(self) -> Address:
        return recover(self.packed_data(), self.signature)

    def channel_id(self) -> ChannelID:
        hashed_id = keccak(
            encode_single("uint256", self.chain_id)
            + self.token_network_address
            + self.owner
            + self.partner
        )
        return ChannelID(int.from_bytes(bytes=hashed_id, byteorder="big"))
