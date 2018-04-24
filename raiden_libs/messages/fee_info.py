# -*- coding: utf-8 -*-
from typing import Dict
import struct

import jsonschema
from eth_utils import is_address, decode_hex

from raiden_libs.messages.message import Message
from raiden_libs.properties import address_property
from raiden_libs.messages.json_schema import FEE_INFO_SCHEMA
from raiden_libs.utils import eth_verify
from raiden_libs.types import Address, ChannelIdentifier


class FeeInfo(Message):
    """ A message to update the fee. It is sent from a raiden node to the PFS. """
    def __init__(
        self,
        token_network_address: Address,
        channel_identifier: ChannelIdentifier,
        chain_id: int = 1,
        nonce: int = 0,
        percentage_fee: float = 0.0,
        signature: str = None,
    ) -> None:
        super().__init__()
        assert channel_identifier >= 0
        assert is_address(token_network_address)

        self._type = 'FeeInfo'

        self.token_network_address = token_network_address
        self.channel_identifier = channel_identifier
        self.chain_id = chain_id
        self.nonce = nonce
        self.percentage_fee = percentage_fee
        self.signature = signature

    def serialize_data(self) -> Dict:
        return {
            'token_network_address': self.token_network_address,
            'channel_identifier': self.channel_identifier,
            'chain_id': self.chain_id,
            'nonce': self.nonce,
            'percentage_fee': str(self.percentage_fee),
            'signature': self.signature,
        }

    def serialize_bin(self):
        """Return FeeInfo serialized to binary"""
        order = '>20s32s32s8sd'
        return struct.pack(
            order,
            decode_hex(self.token_network_address),
            self.channel_identifier.to_bytes(32, byteorder='big'),
            self.chain_id.to_bytes(32, byteorder='big'),
            self.nonce.to_bytes(8, byteorder='big'),
            self.percentage_fee
        )

    @classmethod
    def deserialize(cls, data):
        jsonschema.validate(data, FEE_INFO_SCHEMA)
        ret = cls(
            token_network_address=data['token_network_address'],
            channel_identifier=data['channel_identifier'],
            chain_id=data['chain_id'],
            nonce=data['nonce'],
            percentage_fee=float(data['percentage_fee']),
            signature=data['signature'],
        )

        return ret

    @property
    def signer(self) -> str:
        return eth_verify(
            decode_hex(self.signature),
            self.serialize_bin()
        )

    token_network_address = address_property('_contract')  # type: ignore
    json_schema = FEE_INFO_SCHEMA
