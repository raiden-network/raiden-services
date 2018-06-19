# -*- coding: utf-8 -*-
from typing import Dict

import jsonschema
from eth_utils import is_address, decode_hex, to_checksum_address

from raiden_libs.messages.message import Message
from raiden_libs.properties import address_property
from raiden_libs.messages.json_schema import PATHS_REQUEST_SCHEMA
from raiden_libs.utils import eth_verify, UINT256_MAX, pack_data
from raiden_libs.types import Address


class PathsRequest(Message):
    """ A message to request a path from PFS. It is sent from a raiden node to the PFS. """
    def __init__(
        self,
        token_network_address: Address,
        source_address: Address,
        target_address: Address,
        value: int,
        chain_id: int,
        num_paths: int,
        nonce: int,
        signature: str = None,
    ) -> None:
        super().__init__()
        assert is_address(token_network_address)
        assert is_address(source_address)
        assert is_address(target_address)
        assert 0 <= value <= UINT256_MAX
        assert 0 <= num_paths <= UINT256_MAX
        assert 0 <= nonce <= UINT256_MAX

        self._type = 'PathsRequest'
        self.token_network_address = token_network_address
        self.source_address = source_address
        self.target_address = target_address
        self.value = value
        self.num_paths = num_paths
        self.chain_id = chain_id
        self.nonce = nonce
        self.signature = signature

    def serialize_data(self) -> Dict:
        return {
            'token_network_address': self.token_network_address,
            'source_address': self.source_address,
            'target_address': self.target_address,
            'value': self.value,
            'num_paths': self.num_paths,
            'chain_id': self.chain_id,
            'nonce': self.nonce,
            'signature': self.signature,
        }

    def serialize_bin(self):
        """Returns PathsRequest serialized to binary"""
        return pack_data([
            'address',
            'address',
            'address',
            'uint256',
            'uint256',
            'uint256',
            'uint256',
        ], [
            self.token_network_address,
            self.source_address,
            self.target_address,
            self.value,
            self.num_paths,
            self.chain_id,
            self.nonce,
        ])

    @classmethod
    def deserialize(cls, data):
        jsonschema.validate(data, PATHS_REQUEST_SCHEMA)
        ret = cls(
            token_network_address=data['token_network_address'],
            source_address=data['source_address'],
            target_address=data['target_address'],
            value=data['value'],
            num_paths=data['num_paths'],
            chain_id=data['chain_id'],
            nonce=data['nonce'],
            signature=data['signature'],
        )

        return ret

    @property
    def signer(self) -> str:
        signer = eth_verify(
            decode_hex(self.signature),
            self.serialize_bin(),
        )
        return to_checksum_address(signer)

    token_network_address = address_property('_contract')  # type: ignore
    json_schema = PATHS_REQUEST_SCHEMA
