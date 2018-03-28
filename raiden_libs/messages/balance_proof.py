import jsonschema
import time
import struct

from raiden_libs.messages.message import Message
from raiden_libs.properties import address_property
from raiden_libs.messages.json_schema import BALANCE_PROOF_SCHEMA

from eth_utils import is_address, decode_hex


class BalanceProof(Message):
    def __init__(
            self,
            channel_id: int,
            contract_address: str,
            participant1: str,
            participant2: str,
            nonce: int = 0,
            locksroot: str = '0x%032x' % 0,
            transferred_amount: int = 0,
            extra_hash: str = '0x%032x' % 0,
            chain_id: int = 1
    ) -> None:
        super().__init__()
        assert channel_id > 0
        assert is_address(participant1)
        assert is_address(participant2)
        assert is_address(contract_address)
        self.channel_id = channel_id
        self.contract_address = contract_address
        self.participant1 = participant1
        self.participant2 = participant2
        self._type = 'BalanceProof'
        self.timestamp = time.time()
        self.nonce = nonce
        self.locksroot = locksroot
        self.transferred_amount = transferred_amount
        self.extra_hash = extra_hash
        self.signature = '0x0'
        self.chain_id = chain_id

    def serialize_data(self) -> dict:
        return {
            'channel_id': self.channel_id,
            'participant1': self.participant1,
            'participant2': self.participant2,
            'contract_address': self.contract_address,
            'timestamp': self.timestamp,
            'nonce': self.nonce,
            'locksroot': self.locksroot,
            'extra_hash': self.extra_hash,
            'transferred_amount': self.transferred_amount,
            'signature': self.signature,
            'chain_id': self.chain_id
        }

    def serialize_bin(self):
        # nonce, amount, channel address, locksroot
        order = '>8s32s32s32s20s32s32s'
        assert isinstance(self.channel_id, int)
        assert isinstance(self.nonce, int)
        assert isinstance(self.transferred_amount, int)
        assert isinstance(self.locksroot, (bytes, str))
        assert isinstance(self.extra_hash, (bytes, str))
        assert is_address(self.contract_address)
        return struct.pack(
            order,
            self.nonce.to_bytes(8, byteorder='big'),
            self.transferred_amount.to_bytes(32, byteorder='big'),
            decode_hex(self.locksroot),
            self.channel_id.to_bytes(32, byteorder='big'),
            decode_hex(self.contract_address),
            self.chain_id.to_bytes(32, byteorder='big'),
            decode_hex(self.extra_hash)
        )

    @classmethod
    def deserialize(cls, data):
        jsonschema.validate(data, BALANCE_PROOF_SCHEMA)
        ret = cls(
            data['channel_id'],
            data['contract_address'],
            data['participant1'],
            data['participant2']
        )
        ret.timestamp = data['timestamp']
        return ret

    contract_address = address_property('_contract')  # type: ignore
    participant1 = address_property('_participant1')  # type: ignore
    participant2 = address_property('_participant2')  # type: ignore
    json_schema = BALANCE_PROOF_SCHEMA
