# pylint: disable=redefined-outer-name
import itertools
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from unittest import mock
from unittest.mock import Mock, patch
from uuid import uuid1

import gevent
import pytest
from eth_utils import encode_hex, to_canonical_address
from gevent.event import AsyncResult

from monitoring_service.states import HashedBalanceProof
from raiden.constants import DeviceIDs
from raiden.messages.monitoring_service import RequestMonitoring
from raiden.network.transport.matrix.utils import DisplayNameCache
from raiden.storage.serialization.serializer import DictSerializer, MessageSerializer
from raiden.utils.typing import (
    Address,
    Any,
    ChainID,
    ChannelID,
    Dict,
    MonitoringServiceAddress,
    Nonce,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_contracts.tests.utils import LOCKSROOT_OF_NO_LOCKS, deepcopy
from raiden_libs.matrix import (
    ClientManager,
    MatrixListener,
    RateLimiter,
    deserialize_messages,
    matrix_http_retry_delay,
)
from raiden_libs.utils import MultiClientUserAddressManager
from tests.pathfinding.test_fee_updates import (
    PRIVATE_KEY_1,
    PRIVATE_KEY_1_ADDRESS,
    get_fee_update_message,
)

INVALID_PEER_ADDRESS = Address(to_canonical_address("0x" + "1" * 40))


@pytest.fixture
def request_monitoring_message(token_network, get_accounts, get_private_key) -> RequestMonitoring:
    c1, c2 = get_accounts(2)

    balance_proof_c2 = HashedBalanceProof(
        channel_identifier=ChannelID(1),
        token_network_address=TokenNetworkAddress(to_canonical_address(token_network.address)),
        chain_id=ChainID(61),
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
        monitoring_service_contract_address=MonitoringServiceAddress(bytes([11] * 20)),
    )


@pytest.fixture
def presence_event(server_index: int) -> Dict[str, Any]:

    return {
        "content": {
            "last_active_ago": 2478593,
            "presence": "online",
            "status_msg": "Making cupcakes",
        },
        "sender": f"@example:example0{server_index}.com",
        "type": "m.presence",
    }


@pytest.mark.parametrize("message_data", ["", " \r\n ", "\n ", "@@@"])
def test_deserialize_messages(message_data):
    messages = deserialize_messages(data=message_data, peer_address=INVALID_PEER_ADDRESS)
    assert len(messages) == 0


def test_deserialize_messages_invalid_sender(request_monitoring_message):
    message = MessageSerializer.serialize(request_monitoring_message)

    messages = deserialize_messages(data=message, peer_address=INVALID_PEER_ADDRESS)
    assert len(messages) == 0


def test_deserialize_checks_datetimes_in_messages():
    invalid_fee_update = get_fee_update_message(
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
        timestamp=datetime.now(timezone.utc),
    )
    message = MessageSerializer.serialize(invalid_fee_update)

    messages = deserialize_messages(data=message, peer_address=PRIVATE_KEY_1_ADDRESS)
    assert len(messages) == 0

    valid_fee_update = get_fee_update_message(
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
        timestamp=datetime.utcnow(),
    )
    message = MessageSerializer.serialize(valid_fee_update)

    messages = deserialize_messages(data=message, peer_address=PRIVATE_KEY_1_ADDRESS)
    assert len(messages) == 1


def test_deserialize_messages_valid_message(request_monitoring_message):
    message = MessageSerializer.serialize(request_monitoring_message)

    messages = deserialize_messages(data=message, peer_address=request_monitoring_message.sender)
    assert len(messages) == 1


def test_deserialize_messages_valid_messages(request_monitoring_message):
    message = MessageSerializer.serialize(request_monitoring_message)
    raw_string = message + "\n" + message

    messages = deserialize_messages(
        data=raw_string, peer_address=request_monitoring_message.sender
    )
    assert len(messages) == 2


def test_matrix_http_retry_delay():
    delays = list(itertools.islice(matrix_http_retry_delay(), 8))

    assert delays == [5.0, 10.0, 20.0, 40.0, 60.0, 60.0, 60.0, 60.0]


def test_deserialize_messages_with_missing_fields(request_monitoring_message):
    message_dict = DictSerializer.serialize(request_monitoring_message)
    list_of_key_words = list(message_dict.keys())

    # non closing signature is not required by this message type
    list_of_key_words.remove("non_closing_signature")

    for key in list_of_key_words:
        message_json_broken = deepcopy(message_dict)
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


def test_matrix_listener_smoke_test(get_accounts, get_private_key):
    (c1,) = get_accounts(1)
    client_mock = Mock()
    client_mock.api.base_url = "http://example.com"
    client_mock.user_id = "1"

    with patch.multiple(
        "raiden_libs.matrix",
        make_client=Mock(return_value=client_mock),
        join_broadcast_room=Mock(),
    ):
        listener = MatrixListener(
            private_key=get_private_key(c1),
            chain_id=ChainID(61),
            device_id=DeviceIDs.PFS,
            service_room_suffix="_service",
            message_received_callback=lambda _: None,
        )
        listener._run()  # pylint: disable=protected-access

    assert listener.startup_finished.done()


@pytest.mark.parametrize("server_index", [0, 1, 2, 3, 4])
def test_filter_presences_by_client(presence_event, server_index):

    server_urls = [f"https://example0{i}.com" for i in range(5)]

    uuids_to_callbacks = {}
    server_url_to_clients = {}
    server_url_to_processed_presence = []

    def _mock_add_presence_listener(listener):
        uuid = uuid1()
        uuids_to_callbacks[uuid] = listener
        return uuid

    def _mock_remove_presence_listener(listener_id):
        uuids_to_callbacks.pop(listener_id)

    def _mock_presence_listener(
        self, event: Dict[str, Any], presence_update_id: int  # pylint: disable=unused-argument
    ) -> None:
        server_url_to_processed_presence.append(event)

    for server_url in server_urls:
        client = Mock()
        client.api.base_url = server_url
        client.add_presence_listener = _mock_add_presence_listener
        client.remove_presence_listener = _mock_remove_presence_listener
        server_url_to_clients[server_url] = client

    main_client = server_url_to_clients.pop(server_urls[0])

    with mock.patch.object(
        MultiClientUserAddressManager, "_presence_listener", new=_mock_presence_listener
    ):
        uam = MultiClientUserAddressManager(
            client=main_client,
            displayname_cache=DisplayNameCache(),
        )
        uam.start()

        for client in server_url_to_clients.values():
            uam.add_client(client)

        # call presence listener on all clients
        for listener in uuids_to_callbacks.values():
            listener(presence_event, 0)

        # only the respective client should forward the presence to the uam
        expected_presences = 1

        assert len(server_url_to_processed_presence) == expected_presences

        # drop the client of the last homeserver in the list
        # and remove listener
        client = server_url_to_clients[server_urls[-1]]
        uam.remove_client(client)

        # only call the listener of the main client
        # if the presence event comes from the server with the dropped client
        # it should also consume the presence, otherwise not
        uuids_to_callbacks[uam._listener_id](presence_event, 0)  # pylint: disable=protected-access

        if server_index in [0, len(server_urls) - 1]:
            expected_presences += 1

        assert len(server_url_to_processed_presence) == expected_presences


def test_client_manager_start(get_accounts, get_private_key):
    server_urls = [f"https://example0{i}.com" for i in range(5)]

    (c1,) = get_accounts(1)
    private_key = get_private_key(c1)
    client_mock = Mock()
    client_mock.api.base_url = "https://example00.com"
    client_mock.user_id = "1"
    client_mock.sync_worker = AsyncResult()
    start_client_counter = 0

    def mock_start_client(server_url: str):  # pylint: disable=unused-argument
        nonlocal start_client_counter
        client_mock.sync_worker = AsyncResult()
        start_client_counter += 1
        return client_mock

    with patch.multiple(
        "raiden_libs.matrix",
        make_client=Mock(return_value=client_mock),
        get_matrix_servers=Mock(return_value=server_urls),
        login=Mock(),
        join_broadcast_room=Mock(),
    ):
        client_manager = ClientManager(
            available_servers=[f"https://example0{i}.com" for i in range(5)],
            broadcast_room_alias_prefix="_service",
            chain_id=ChainID(1),
            device_id=DeviceIDs.PFS,
            private_key=private_key,
            handle_matrix_sync=lambda s: True,
        )

        client_manager._start_client = mock_start_client  # pylint: disable=protected-access

        assert client_manager.known_servers == server_urls

        uam = MultiClientUserAddressManager(
            client=client_manager.main_client,
            displayname_cache=DisplayNameCache(),
        )
        uam.start()
        client_manager.user_manager = uam
        client_manager.stop_event.clear()

        gevent.spawn(client_manager.connect_client_forever, client_mock.api.base_url)
        gevent.sleep(2)
        client_mock.sync_worker.set(True)
        gevent.sleep(2)
        client_manager.stop_event.set()
        client_mock.sync_worker.set(True)

        assert start_client_counter == 2
