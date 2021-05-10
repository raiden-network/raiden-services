import sys
from datetime import datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import gevent
import structlog
from eth_utils import to_checksum_address
from gevent.event import AsyncResult, Event
from gevent.greenlet import Greenlet
from marshmallow import ValidationError
from matrix_client.errors import MatrixRequestError
from matrix_client.user import User

from monitoring_service.constants import (
    MATRIX_RATE_LIMIT_ALLOWED_BYTES,
    MATRIX_RATE_LIMIT_RESET_INTERVAL,
)
from raiden.constants import DeviceIDs, Environment, MatrixMessageType, Networks
from raiden.exceptions import SerializationError, TransportError
from raiden.messages.abstract import Message, SignedMessage
from raiden.network.transport.matrix.client import (
    GMatrixClient,
    MatrixMessage,
    MatrixSyncMessages,
    Room,
)
from raiden.network.transport.matrix.utils import (
    DisplayNameCache,
    login,
    make_client,
    validate_user_id_signature,
)
from raiden.network.transport.utils import timeout_exponential_backoff
from raiden.settings import (
    DEFAULT_MATRIX_KNOWN_SERVERS,
    DEFAULT_TRANSPORT_MATRIX_RETRY_INTERVAL_INITIAL,
    DEFAULT_TRANSPORT_MATRIX_RETRY_INTERVAL_MAX,
    DEFAULT_TRANSPORT_MATRIX_SYNC_LATENCY,
    DEFAULT_TRANSPORT_MATRIX_SYNC_TIMEOUT,
    DEFAULT_TRANSPORT_RETRIES_BEFORE_BACKOFF,
)
from raiden.storage.serialization.serializer import MessageSerializer
from raiden.utils.cli import get_matrix_servers
from raiden.utils.signer import LocalSigner
from raiden.utils.typing import Address, ChainID, Set
from raiden_contracts.utils.type_aliases import PrivateKey
from raiden_libs.utils import MultiClientUserAddressManager

log = structlog.get_logger(__name__)


class RateLimiter:
    """Primitive bucket based rate limiter

    Counts bytes for each sender. `check_and_count` will return false when the
    `allowed_bytes` are exceeded during a single `reset_interval`.
    """

    def __init__(self, allowed_bytes: int, reset_interval: timedelta):
        self.allowed_bytes = allowed_bytes
        self.reset_interval = reset_interval
        self.next_reset = datetime.utcnow() + reset_interval
        self.bytes_processed_for: Dict[Address, int] = {}

    def reset_if_it_is_time(self) -> None:
        if datetime.utcnow() >= self.next_reset:
            self.bytes_processed_for = {}
            self.next_reset = datetime.utcnow() + self.reset_interval

    def check_and_count(self, sender: Address, added_bytes: int) -> bool:
        new_total = self.bytes_processed_for.get(sender, 0) + added_bytes
        if new_total > self.allowed_bytes:
            return False

        self.bytes_processed_for[sender] = new_total
        return True


def deserialize_messages(
    data: str, peer_address: Address, rate_limiter: Optional[RateLimiter] = None
) -> List[SignedMessage]:
    messages: List[SignedMessage] = list()

    if rate_limiter:
        rate_limiter.reset_if_it_is_time()
        # This size includes some bytes of overhead for python. But otherwise we
        # would have to either count characters for decode the whole string before
        # checking the rate limiting.
        size = sys.getsizeof(data)
        if not rate_limiter.check_and_count(peer_address, size):
            log.warning("Sender is rate limited", sender=peer_address)
            return []

    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue

        logger = log.bind(peer_address=to_checksum_address(peer_address))
        try:
            message = MessageSerializer.deserialize(line)
        except (SerializationError, ValidationError, KeyError, ValueError) as ex:
            logger.warning("Message data JSON is not a valid message", message_data=line, _exc=ex)
            continue

        if not isinstance(message, SignedMessage):
            logger.warning("Received invalid message", message=message)
            continue

        if message.sender != peer_address:
            logger.warning("Message not signed by sender!", message=message, signer=message.sender)
            continue

        messages.append(message)

    return messages


def matrix_http_retry_delay() -> Iterable[float]:
    return timeout_exponential_backoff(
        DEFAULT_TRANSPORT_RETRIES_BEFORE_BACKOFF,
        DEFAULT_TRANSPORT_MATRIX_RETRY_INTERVAL_INITIAL,
        DEFAULT_TRANSPORT_MATRIX_RETRY_INTERVAL_MAX,
    )


class MatrixListener(gevent.Greenlet):
    # pylint: disable=too-many-instance-attributes
    def __init__(
        self,
        private_key: PrivateKey,
        chain_id: ChainID,
        device_id: DeviceIDs,
        message_received_callback: Callable[[Message], None],
        servers: Optional[List[str]] = None,
    ) -> None:
        super().__init__()

        self.chain_id = chain_id
        self.device_id = device_id
        self.message_received_callback = message_received_callback
        self._displayname_cache = DisplayNameCache()
        self.startup_finished = AsyncResult()
        self._client_manager = ClientManager(
            available_servers=servers,
            device_id=self.device_id,
            chain_id=self.chain_id,
            private_key=private_key,
            handle_matrix_sync=self._handle_matrix_sync,
        )

        self.base_url = self._client.api.base_url
        self.user_manager = MultiClientUserAddressManager(
            client=self._client,
            displayname_cache=self._displayname_cache,
        )

        self._rate_limiter = RateLimiter(
            allowed_bytes=MATRIX_RATE_LIMIT_ALLOWED_BYTES,
            reset_interval=MATRIX_RATE_LIMIT_RESET_INTERVAL,
        )

    @property
    def _client(self) -> GMatrixClient:
        return self._client_manager.main_client

    @property
    def server_url_to_other_clients(self) -> Dict[str, GMatrixClient]:
        return self._client_manager.server_url_to_other_clients

    def _run(self) -> None:  # pylint: disable=method-hidden

        self.user_manager.start()
        self._client_manager.start(self.user_manager)

        def set_startup_finished() -> None:
            self._client.processed.wait()
            self.startup_finished.set()

        startup_finished_greenlet = gevent.spawn(set_startup_finished)
        try:
            assert self._client.sync_worker
            self._client.sync_worker.get()
        finally:
            self._client_manager.stop()
            gevent.joinall({startup_finished_greenlet}, raise_error=True, timeout=0)

    def _handle_matrix_sync(self, messages: MatrixSyncMessages) -> bool:
        all_messages: List[Message] = list()
        for room, room_messages in messages:
            if room is not None:
                # Ignore room messages
                # This will only handle to-device messages
                continue

            for text in room_messages:
                all_messages.extend(self._handle_message(room, text))

        log.debug("Incoming messages", messages=all_messages)

        for message in all_messages:
            self.message_received_callback(message)

        return True

    def _handle_message(self, room: Optional[Room], message: MatrixMessage) -> List[SignedMessage]:
        """Handle a single Matrix message.

        The matrix message is expected to be a NDJSON, and each entry should be
        a valid JSON encoded Raiden message.

        If `room` is None this means we are processing a `to_device` message
        """
        is_valid_type = (
            message["type"] == "m.room.message"
            and message["content"]["msgtype"] == MatrixMessageType.TEXT.value
        )
        if not is_valid_type:
            return []

        sender_id = message["sender"]
        self._displayname_cache.warm_users([User(self._client.api, sender_id)])
        # handles the "Could not get 'display_name' for user" case

        try:
            displayname = self._displayname_cache.userid_to_displayname[sender_id]
        except KeyError as ex:
            log.error("Could not warm display cache", peer_user=sender_id, error=str(ex))
            return []

        peer_address = validate_user_id_signature(sender_id, displayname)

        if not peer_address:
            log.debug(
                "Message from invalid user displayName signature",
                peer_user=sender_id,
                room=room,
            )
            return []

        data = message["content"]["body"]
        if not isinstance(data, str):
            log.warning(
                "Received message body not a string",
                peer_user=sender_id,
                peer_address=to_checksum_address(peer_address),
                room=room,
            )
            return []

        messages = deserialize_messages(
            data=data, peer_address=peer_address, rate_limiter=self._rate_limiter
        )
        if not messages:
            return []

        return messages


class ClientManager:
    # pylint: disable=too-many-instance-attributes
    def __init__(
        self,
        available_servers: Optional[List[str]],
        device_id: DeviceIDs,
        chain_id: ChainID,
        private_key: bytes,
        handle_matrix_sync: Callable[[MatrixSyncMessages], bool],
    ):
        self.user_manager: Optional[MultiClientUserAddressManager] = None
        self.local_signer = LocalSigner(private_key=private_key)
        self.device_id = device_id
        self.chain_id = chain_id
        self.stop_event = Event()
        self.stop_event.set()

        try:
            self.known_servers = (
                get_matrix_servers(
                    DEFAULT_MATRIX_KNOWN_SERVERS[Environment.PRODUCTION]
                    if chain_id == 1
                    else DEFAULT_MATRIX_KNOWN_SERVERS[Environment.DEVELOPMENT]
                )
                if chain_id
                in [
                    Networks.MAINNET.value,
                    Networks.ROPSTEN.value,
                    Networks.RINKEBY.value,
                    Networks.GOERLI.value,
                    Networks.KOVAN.value,
                ]
                else []
            )

        except RuntimeError:
            if available_servers is None:
                raise
            self.known_servers = []

        if available_servers:
            self.available_servers = available_servers
        else:
            self.available_servers = self.known_servers

        self.main_client = make_client(
            handle_messages_callback=handle_matrix_sync,
            servers=self.available_servers,
            http_pool_maxsize=4,
            http_retry_timeout=40,
            http_retry_delay=matrix_http_retry_delay,
        )
        self.server_url_to_other_clients: Dict[str, GMatrixClient] = {}
        self.connect_client_workers: Set[Greenlet] = set()

    @property
    def server_url_to_all_clients(self) -> Dict[str, GMatrixClient]:
        return {
            **self.server_url_to_other_clients,
            urlparse(self.main_client.api.base_url).netloc: self.main_client,
        }

    def start(self, user_manager: MultiClientUserAddressManager) -> None:
        self.stop_event.clear()
        self.user_manager = user_manager
        try:
            self._start_client(self.main_client.api.base_url)
        except (TransportError, ConnectionError, MatrixRequestError) as ex:
            log.error(
                "Could not connect to main client",
                server_url=self.main_client.api.base_url,
                exception=ex,
            )
            return

        for server_url in [
            server_url
            for server_url in self.known_servers
            if server_url != self.main_client.api.base_url
        ]:
            connect_worker = gevent.spawn(self.connect_client_forever, server_url)
            self.connect_client_workers.add(connect_worker)

    def stop(self) -> None:
        assert self.user_manager, "Stop called before start"

        self.stop_event.set()
        for server_url, client in self.server_url_to_all_clients.items():
            self.server_url_to_other_clients.pop(server_url, None)
            client.stop_listener_thread()
            self.user_manager.remove_client(client)

        gevent.joinall(self.connect_client_workers, raise_error=True)

    def connect_client_forever(self, server_url: str) -> None:
        assert self.user_manager
        while not self.stop_event.is_set():
            stopped_client = self.server_url_to_other_clients.pop(server_url, None)
            if stopped_client is not None:
                self.user_manager.remove_client(stopped_client)
            try:
                client = self._start_client(server_url)
                assert client.sync_worker is not None
                client.sync_worker.get()
            except (TransportError, ConnectionError) as ex:
                log.error("Could not connect to server", server_url=server_url, exception=ex)
            except MatrixRequestError as ex:
                log.error(
                    "A Matrix Error occurred during sync", server_url=server_url, exception=ex
                )
            except Exception as ex:
                log.error(
                    "An unhandled Exception occurred during sync. Restarting PFS.",
                    server_url=server_url,
                    exception=ex,
                )
                self.main_client.stop()
                raise

    def _start_client(self, server_url: str) -> GMatrixClient:
        assert self.user_manager
        if self.stop_event.is_set():
            raise TransportError()

        if server_url == self.main_client.api.base_url:
            client = self.main_client
        else:
            # Also handle messages on the other clients,
            # since to-device communication to the PFS only happens via the local user
            # on each homeserver
            client = make_client(
                handle_messages_callback=self.main_client.handle_messages_callback,
                servers=[server_url],
                http_pool_maxsize=4,
                http_retry_timeout=40,
                http_retry_delay=matrix_http_retry_delay,
            )

            self.server_url_to_other_clients[server_url] = client
            log.debug("Created client for other server", server_url=server_url)
        try:
            login(client, signer=self.local_signer, device_id=self.device_id)
            log.debug("Matrix login successful", server_url=server_url)

        except (MatrixRequestError, ValueError):
            raise ConnectionError("Could not login/register to matrix.")

        client.start_listener_thread(
            DEFAULT_TRANSPORT_MATRIX_SYNC_TIMEOUT,
            DEFAULT_TRANSPORT_MATRIX_SYNC_LATENCY,
        )

        # main client is already added upon MultiClientUserAddressManager.start()
        if server_url != self.main_client.api.base_url:
            self.user_manager.add_client(client)
        return client
