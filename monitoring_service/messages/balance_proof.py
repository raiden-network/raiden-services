import jsonschema
import time

from monitoring_service.messages.message import Message
from monitoring_service.properties import address_property
from monitoring_service.json_schema import BALANCE_PROOF_SCHEMA


class BalanceProof(Message):
    def __init__(self, channel_address, participant1, participant2):
        super().__init__()
        self.channel_address = channel_address
        self.participant1 = participant1
        self.participant2 = participant2
        self._type = 'BalanceProof'
        self.timestamp = time.time()

    def serialize_data(self):
        return {
            'participant1': self.participant1,
            'participant2': self.participant2,
            'channel_address': self.channel_address,
            'balance_proof': '0x666',
            'timestamp': self.timestamp
        }

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
