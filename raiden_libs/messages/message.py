import json
from typing import Type

import jsonschema
from eth_utils import encode_hex

from raiden_libs.utils import eth_sign
from raiden_libs.messages.deserializer import deserialize
from raiden_libs.messages.json_schema import ENVELOPE_SCHEMA
from raiden_libs.exceptions import MessageTypeError


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

    def serialize_full(self):
        """Serialize message to a standardized format, including message envelope"""
        msg = self.serialize_data()
        msg['message_type'] = self._type
        return json.dumps(msg)

    def sign_data(self, private_key, data: str):
        return encode_hex(eth_sign(private_key, data.encode()))

    @staticmethod
    def deserialize(data, type: Type = None) -> 'Message':
        """ Deserializes a message.

        Args:
            data: The message data
            type: An optional message type. If this is set and the message in `data`
                has a different type, a `MessageTypeError` is raised.

        Returns:
            The deserialized `Message`
        """
        if isinstance(data, str):
            json_message = json.loads(data)
        else:
            json_message = data
        jsonschema.validate(json_message, Message.json_schema)

        message_type = json_message.get('message_type', None)
        if type and type.__name__ != message_type:
            raise MessageTypeError

        return deserialize(json_message)
