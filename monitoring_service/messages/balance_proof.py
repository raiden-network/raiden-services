import jsonschema
import time
import struct

from monitoring_service.messages.message import Message
from monitoring_service.properties import address_property
from monitoring_service.json_schema import BALANCE_PROOF_SCHEMA

from eth_utils import is_address, decode_hex


class BalanceProof(Message):
    def __init__(self, channel_address, participant1, participant2,
                 nonce=0,
                 locksroot='0x%032x' % 0,
                 transferred_amount=0,
                 extra_hash='0x%032x' % 0
                 ):
        super().__init__()
        assert is_address(channel_address)
        assert is_address(participant1)
        assert is_address(participant2)
        self.channel_address = channel_address
        self.participant1 = participant1
        self.participant2 = participant2
        self._type = 'BalanceProof'
        self.timestamp = time.time()
        self.nonce = nonce
        self.locksroot = locksroot
        self.transferred_amount = transferred_amount
        self.extra_hash = extra_hash
        self.signature = '0x0'

    def serialize_data(self):
        return {
            'participant1': self.participant1,
            'participant2': self.participant2,
            'channel_address': self.channel_address,
            'balance_proof': '0x666',
            'timestamp': self.timestamp,
            'nonce': self.nonce,
            'locksroot': self.locksroot,
            'extra_hash': self.extra_hash,
            'transferred_amount': self.transferred_amount,
            'signature': self.signature
        }

    def serialize_bin(self):
        # nonce, amount, channel address, locksroot
        order = '>8s32s32s20s32s'
        assert isinstance(self.nonce, int)
        assert isinstance(self.transferred_amount, int)
        assert isinstance(self.locksroot, (bytes, str))
        assert isinstance(self.extra_hash, (bytes, str))
        return struct.pack(
            order,
            self.nonce.to_bytes(8, byteorder='big'),
            self.transferred_amount.to_bytes(32, byteorder='big'),
            decode_hex(self.locksroot),
            decode_hex(self.channel_address),
            decode_hex(self.extra_hash)
        )

    @classmethod
    def deserialize(cls, data):
        jsonschema.validate(data, BALANCE_PROOF_SCHEMA)
        ret = cls(data['channel_address'],
                  data['participant1'],
                  data['participant2']
                  )
        ret.timestamp = data['timestamp']
        return ret

    channel_address = address_property('_channel')
    participant1 = address_property('_participant1')
    participant2 = address_property('_participant2')
    json_schema = BALANCE_PROOF_SCHEMA
