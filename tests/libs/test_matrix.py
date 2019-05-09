# pylint: disable=redefined-outer-name
import itertools
import json
from unittest.mock import Mock, patch

import pytest
from eth_utils import decode_hex, encode_hex, to_canonical_address

from monitoring_service.states import HashedBalanceProof
from raiden.exceptions import InvalidProtocolMessage
from raiden.messages import RequestMonitoring
from raiden.utils.typing import Address as BytesAddress, ChainID, ChannelID, Nonce, TokenAmount
from raiden_contracts.tests.utils import EMPTY_LOCKSROOT
from raiden_libs.matrix import deserialize_messages, matrix_http_retry_delay, message_from_dict

INVALID_PEER_ADDRESS = BytesAddress(to_canonical_address("0x" + "1" * 40))


@pytest.fixture
def request_monitoring_message(token_network, get_accounts, get_private_key) -> RequestMonitoring:
    c1, c2 = get_accounts(2)

    balance_proof_c2 = HashedBalanceProof(
        token_network_address=decode_hex(token_network.address),
        channel_identifier=ChannelID(1),
        chain_id=ChainID(1),
        nonce=Nonce(2),
        additional_hash="0x%064x" % 0,
        transferred_amount=TokenAmount(1),
        locked_amount=TokenAmount(0),
        locksroot=encode_hex(EMPTY_LOCKSROOT),
        priv_key=get_private_key(c2),
    )

    return balance_proof_c2.get_request_monitoring(
        privkey=get_private_key(c1), reward_amount=TokenAmount(1)
    )


def test_message_from_dict(request_monitoring_message):
    message_json = request_monitoring_message.to_dict()

    # Test happy path
    message = message_from_dict(message_json)
    assert message == request_monitoring_message

    # Test unknown message type
    message_json["type"] = "SomeNonexistantMessage"
    with pytest.raises(InvalidProtocolMessage) as excinfo:
        message_from_dict(message_json)

    assert 'Invalid message type (data["type"]' in str(excinfo.value)

    # Test non-existant message type
    del message_json["type"]
    with pytest.raises(InvalidProtocolMessage) as excinfo:
        message_from_dict(message_json)

    assert "Invalid message data. Can not find the data type" in str(excinfo.value)


@pytest.mark.parametrize("message_data", ["", " \r\n ", "\n ", "@@@"])
def test_deserialize_messages(message_data):
    messages = deserialize_messages(data=message_data, peer_address=INVALID_PEER_ADDRESS)
    assert len(messages) == 0


def test_deserialize_messages_invalid_message_type(request_monitoring_message):
    message_json = request_monitoring_message.to_dict()
    message_json["type"] = "SomeNonexistantMessage"

    messages = deserialize_messages(
        data=json.dumps(message_json), peer_address=INVALID_PEER_ADDRESS
    )
    assert len(messages) == 0


def test_deserialize_messages_invalid_message_class(request_monitoring_message):
    message_json = request_monitoring_message.to_dict()

    with patch("raiden_libs.matrix.message_from_dict", new=Mock()):
        messages = deserialize_messages(
            data=json.dumps(message_json), peer_address=INVALID_PEER_ADDRESS
        )
        assert len(messages) == 0


def test_deserialize_messages_invalid_sender(request_monitoring_message):
    message_json = request_monitoring_message.to_dict()

    messages = deserialize_messages(
        data=json.dumps(message_json), peer_address=INVALID_PEER_ADDRESS
    )
    assert len(messages) == 0


def test_deserialize_messages_valid_message(request_monitoring_message):
    message_json = request_monitoring_message.to_dict()

    messages = deserialize_messages(
        data=json.dumps(message_json), peer_address=request_monitoring_message.sender
    )
    assert len(messages) == 1


def test_deserialize_messages_valid_messages(request_monitoring_message):
    message_json = request_monitoring_message.to_dict()
    raw_string = json.dumps(message_json) + "\n" + json.dumps(message_json)

    messages = deserialize_messages(
        data=raw_string, peer_address=request_monitoring_message.sender
    )
    assert len(messages) == 2


def test_matrix_http_retry_delay():
    delays = list(itertools.islice(matrix_http_retry_delay(), 8))

    assert delays == [1, 1, 1, 1, 1, 2, 4, 5]
