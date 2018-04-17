import json
import jsonschema
from eth_utils import encode_hex
from raiden_libs.utils import sign, keccak256
from raiden_libs.messages.deserializer import deserialize
from raiden_libs.messages.json_schema import ENVELOPE_SCHEMA


class Message:
    """Generic Raiden message"""
    json_schema = ENVELOPE_SCHEMA

    def __init__(self):
        self._type = None

    def serialize_data(self) -> dict:
        """get message data as a dict"""
        raise NotImplementedError

    @classmethod
    def deserialize_from_json(cls, data):
        """Deserialize JSON into a message instance"""
        raise NotImplementedError

    @property
    def type(self):
        return self._type

    @type.setter
    def type(self, value):
        assert isinstance(self._type, str)
        self._type = value

    def serialize_full(self, private_key):
        """Serialize message to a standardized format, including message envelope"""
        msg = self.serialize_data()
        msg['message_type'] = self._type
        return json.dumps(msg)

    def sign_data(self, private_key, data: str):
        data_hash = keccak256(data)
        return encode_hex(sign(private_key, data_hash))

    @staticmethod
    def deserialize(data):
        if isinstance(data, str):
            json_message = json.loads(data)
        else:
            json_message = data
        jsonschema.validate(json_message, Message.json_schema)
        cls = deserialize(json_message)
        return cls
