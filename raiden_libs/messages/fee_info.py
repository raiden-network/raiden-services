# -*- coding: utf-8 -*-
from typing import Dict

import jsonschema

from raiden_libs.messages.message import Message
from raiden_libs.properties import address_property
from raiden_libs.messages.json_schema import FEE_INFO_SCHEMA

from eth_utils import is_address


class FeeInfo(Message):
    """ A message to update the fee. It is sent from a raiden node to the PFS. """
    def __init__(
        self,
        token_network_address: str,
        channel_identifier: int,
        signature: str,
        nonce: int = 0,
        base_fee: int = 0,
        percentage_fee: float = 0.0,
        chain_id: int = 1,
    ) -> None:
        super().__init__()
        assert channel_identifier > 0
        assert is_address(token_network_address)
        assert base_fee > 0

        self._type = 'FeeInfo'

        self.token_network_address = token_network_address
        self.channel_identifier = channel_identifier
        self.signature = signature
        self.nonce = nonce
        self.base_fee = base_fee
        self.percentage_fee = percentage_fee
        self.chain_id = chain_id

    def serialize_data(self) -> Dict:
        return {
            'token_network_address': self.token_network_address,
            'channel_identifier': self.channel_identifier,
            'nonce': self.nonce,
            'base_fee': self.base_fee,
            'percentage_fee': str(self.percentage_fee),
            'chain_id': self.chain_id,
            'signature': self.signature,
        }

    @classmethod
    def deserialize(cls, data: Dict) -> 'FeeInfo':
        jsonschema.validate(data, FEE_INFO_SCHEMA)
        ret = cls(
            token_network_address=data['token_network_address'],
            channel_identifier=data['channel_identifier'],
            signature=data['signature'],
            nonce=data['nonce'],
            base_fee=data['base_fee'],
            percentage_fee=data['percentage_fee'],
            chain_id=data['chain_id']
        )

        return ret

    token_network_address = address_property('_contract')  # type: ignore
    json_schema = FEE_INFO_SCHEMA
