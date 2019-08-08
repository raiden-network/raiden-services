# pylint: disable=redefined-outer-name
import itertools
import json
import sys
import time
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from eth_utils import encode_hex, to_canonical_address

from monitoring_service.states import HashedBalanceProof
from raiden.exceptions import SerializationError
from raiden.messages.monitoring_service import RequestMonitoring
from raiden.storage.serialization.serializer import DictSerializer
from raiden.utils.typing import (
    Address,
    ChainID,
    ChannelID,
    Nonce,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_contracts.tests.utils import LOCKSROOT_OF_NO_LOCKS, deepcopy
from raiden_libs.matrix import (
    MatrixListener,
    RateLimiter,
    deserialize_messages,
    matrix_http_retry_delay,
    message_from_dict,
)

INVALID_PEER_ADDRESS = Address(to_canonical_address("0x" + "1" * 40))


@pytest.fixture
def request_monitoring_message(token_network, get_accounts, get_private_key) -> RequestMonitoring:
    c1, c2 = get_accounts(2)

    balance_proof_c2 = HashedBalanceProof(
        channel_identifier=ChannelID(1),
        token_network_address=TokenNetworkAddress(to_canonical_address(token_network.address)),
        chain_id=ChainID(1),
        nonce=Nonce(2),
        additional_hash="0x%064x" % 0,
        transferred_amount=TokenAmount(1),
        locked_amount=TokenAmount(0),
        locksroot=encode_hex(LOCKSROOT_OF_NO_LOCKS),
        priv_key=get_private_key(c2),
    )

    return balance_proof_c2.get_request_monitoring(
        privkey=get_private_key(c1),
        reward_amount=TokenAmount(1),
        monitoring_service_contract_address=Address(bytes([11] * 20)),
    )


def test_message_from_dict(request_monitoring_message):
    message_json = DictSerializer.serialize(request_monitoring_message)

    # Test happy path
    message = message_from_dict(message_json)
    assert message == request_monitoring_message

    # Test unknown message type
    message_json["_type"] = "SomeNonexistantMessage"
    with pytest.raises(SerializationError) as excinfo:
        message_from_dict(message_json)

    assert 'Invalid message type (data["type"]' in str(excinfo.value)

    # Test non-existant message type
    del message_json["_type"]
    with pytest.raises(SerializationError) as excinfo:
        message_from_dict(message_json)

    assert "Invalid message data. Can not find the data type" in str(excinfo.value)


@pytest.mark.parametrize("message_data", ["", " \r\n ", "\n ", "@@@"])
def test_deserialize_messages(message_data):
    messages = deserialize_messages(data=message_data, peer_address=INVALID_PEER_ADDRESS)
    assert len(messages) == 0


def test_deserialize_messages_invalid_message_class(request_monitoring_message):
    message_json = DictSerializer.serialize(request_monitoring_message)

    with patch("raiden_libs.matrix.message_from_dict", new=Mock()):
        messages = deserialize_messages(
            data=json.dumps(message_json), peer_address=INVALID_PEER_ADDRESS
        )
        assert len(messages) == 0


def test_deserialize_messages_invalid_sender(request_monitoring_message):
    message_json = DictSerializer.serialize(request_monitoring_message)

    messages = deserialize_messages(
        data=json.dumps(message_json), peer_address=INVALID_PEER_ADDRESS
    )
    assert len(messages) == 0


def test_deserialize_messages_valid_message(request_monitoring_message):
    message_json = DictSerializer.serialize(request_monitoring_message)

    messages = deserialize_messages(
        data=json.dumps(message_json), peer_address=request_monitoring_message.sender
    )
    assert len(messages) == 1


def test_deserialize_messages_valid_messages(request_monitoring_message):
    message_json = DictSerializer.serialize(request_monitoring_message)
    raw_string = json.dumps(message_json) + "\n" + json.dumps(message_json)

    messages = deserialize_messages(
        data=raw_string, peer_address=request_monitoring_message.sender
    )
    assert len(messages) == 2


def test_matrix_http_retry_delay():
    delays = list(itertools.islice(matrix_http_retry_delay(), 8))

    assert delays == [1, 1, 1, 1, 1, 2, 4, 5]


def test_deserialize_messages_with_missing_fields(request_monitoring_message):
    message_json = DictSerializer.serialize(request_monitoring_message)
    list_of_key_words = list(message_json.keys())

    # non closing signature is not required by this message type
    list_of_key_words.remove("non_closing_signature")

    for key in list_of_key_words:
        message_json_broken = deepcopy(message_json)
        del message_json_broken[key]
        messages = deserialize_messages(
            data=json.dumps(message_json_broken), peer_address=request_monitoring_message.sender
        )
        assert len(messages) == 0


def test_deserialize_messages_that_is_too_big(request_monitoring_message, capsys):

    data = str(b"/0" * 1000000)
    assert sys.getsizeof(data) >= 1000000

    deserialize_messages(
        data=data,
        peer_address=request_monitoring_message.sender,
        rate_limiter=RateLimiter(allowed_bytes=1000000, reset_interval=timedelta(minutes=1)),
    )
    captured = capsys.readouterr()

    assert "Sender is rate limited" in captured.out


def test_rate_limiter():
    limiter = RateLimiter(allowed_bytes=100, reset_interval=timedelta(seconds=0.1))
    sender = Address(b"1" * 20)
    for _ in range(50):
        assert limiter.check_and_count(sender=sender, added_bytes=2)

    assert not limiter.check_and_count(sender=sender, added_bytes=2)
    limiter.reset_if_it_is_time()
    assert not limiter.check_and_count(sender=sender, added_bytes=2)
    time.sleep(0.1)
    limiter.reset_if_it_is_time()
    assert limiter.check_and_count(sender=sender, added_bytes=2)


def test_matrix_lister_smoke_test(get_accounts, get_private_key):
    c1, = get_accounts(1)
    url = "http://example.com"
    client_mock = Mock()
    client_mock.api.base_url = url
    client_mock.user_id = "1"
    with patch.multiple(
        "raiden_libs.matrix",
        get_matrix_servers=Mock(return_value=[url]),
        make_client=Mock(return_value=client_mock),
        join_global_room=Mock(),
    ):
        listener = MatrixListener(
            private_key=get_private_key(c1),
            chain_id=ChainID(1),
            service_room_suffix="_service",
            message_received_callback=lambda _: None,
            address_reachability_changed_callback=lambda _addr, _reachability: None,
        )
        listener._start_client()  # pylint: disable=protected-access

    assert listener.startup_finished.is_set()
