from typing import Dict

import jsonschema
from eth_utils import is_address, decode_hex, to_checksum_address

from raiden_libs.messages.message import Message
from raiden_libs.properties import address_property
from raiden_libs.messages.json_schema import FEE_INFO_SCHEMA
from raiden_libs.utils import eth_recover, pack_data
from raiden_libs.types import Address, ChannelIdentifier, T_ChannelIdentifier


class FeeInfo(Message):
    """ A message to update the fee. It is sent from a raiden node to the PFS. """
    def __init__(
        self,
        token_network_address: Address,
        channel_identifier: ChannelIdentifier,
        chain_id: int = 1,
        nonce: int = 0,
        relative_fee: int = 0,  # in parts per million
        signature: str = None,
    ) -> None:
        """ Creates a new FeeInfo message

        Args:
            relative_fee: The fee defined in parts per million, e.g. a value of 10000
                corresponds to a relative fee of one percent.
        """
        super().__init__()
        assert isinstance(channel_identifier, T_ChannelIdentifier)
        assert is_address(token_network_address)

        self._type = 'FeeInfo'

        self.token_network_address = token_network_address
        self.channel_identifier = channel_identifier
        self.chain_id = chain_id
        self.nonce = nonce
        self.relative_fee = relative_fee
        self.signature = signature

    def serialize_data(self) -> Dict:
        return {
            'token_network_address': self.token_network_address,
            'channel_identifier': self.channel_identifier,
            'chain_id': self.chain_id,
            'nonce': self.nonce,
            'relative_fee': self.relative_fee,
            'signature': self.signature,
        }

    def serialize_bin(self) -> bytes:
        """Return FeeInfo serialized to binary"""
        return pack_data([
            'address',
            'uint256',
            'uint256',
            'uint256',
            'uint256',
        ], [
            self.token_network_address,
            self.channel_identifier,
            self.chain_id,
            self.nonce,
            self.relative_fee,
        ])

    @classmethod
    def deserialize(cls, data):
        jsonschema.validate(data, FEE_INFO_SCHEMA)
        ret = cls(
            token_network_address=data['token_network_address'],
            channel_identifier=data['channel_identifier'],
            chain_id=data['chain_id'],
            nonce=data['nonce'],
            relative_fee=data['relative_fee'],
            signature=data['signature'],
        )

        return ret

    @property
    def signer(self) -> str:
        signer = eth_recover(
            data=self.serialize_bin(),
            signature=decode_hex(self.signature),
        )
        return to_checksum_address(signer)

    token_network_address = address_property('_contract')  # type: ignore
    json_schema = FEE_INFO_SCHEMA
