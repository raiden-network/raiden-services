import sys
from datetime import datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import gevent
import structlog
from eth_utils import to_checksum_address
from gevent.event import AsyncResult
from marshmallow import ValidationError
from matrix_client.errors import MatrixRequestError
from matrix_client.user import User

from monitoring_service.constants import (
    MATRIX_RATE_LIMIT_ALLOWED_BYTES,
    MATRIX_RATE_LIMIT_RESET_INTERVAL,
)
from raiden.constants import Environment
from raiden.exceptions import SerializationError, TransportError
from raiden.messages.abstract import Message, SignedMessage
from raiden.network.transport.matrix.client import MatrixMessage, MatrixSyncMessages, Room
from raiden.network.transport.matrix.utils import (
    AddressReachability,
    DisplayNameCache,
    UserAddressManager,
    MultiListenerUserAddressManager,
    join_broadcast_room,
    login,
    make_multiple_clients,
    make_room_alias,
    validate_userid_signature,
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
from raiden.utils.typing import Address, ChainID, PeerCapabilities, RoomID
from raiden_contracts.utils.type_aliases import PrivateKey

log = structlog.get_logger(__name__)


def noop_reachability(  # pylint: disable=unused-argument
    address: Address, reachability: AddressReachability, capabilities: PeerCapabilities
) -> None:
    """A reachability callback is required by the UserAddressManager."""


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
        service_room_suffix: str,
        message_received_callback: Callable[[Message], None],
        servers: Optional[List[str]] = None,
        server_local_presence_updates = False  # FIXME typing Boolean
    ) -> None:
        super().__init__()

        self.private_key = private_key
        self.chain_id = chain_id
        self.service_room_suffix = service_room_suffix
        self.message_received_callback = message_received_callback

        if servers:
            self.available_servers = servers
        else:
            self.available_servers = get_matrix_servers(
                DEFAULT_MATRIX_KNOWN_SERVERS[Environment.PRODUCTION]
                if chain_id == 1
                else DEFAULT_MATRIX_KNOWN_SERVERS[Environment.DEVELOPMENT]
            )


        self._client, *self._other_clients = make_multiple_clients(
            handle_messages_callback=self._handle_matrix_sync,
            handle_member_join_callback=lambda room: None,
            servers=self.available_servers,
            max_num_clients=len(self.available_servers) if server_local_presence_updates else 1,
            http_pool_maxsize=4,
            http_retry_timeout=40,
            http_retry_delay=matrix_http_retry_delay,
        )

        self.broadcast_room_id: Optional[RoomID] = None
        self._broadcast_room: Optional[Room] = None
        self._displayname_cache = DisplayNameCache()
        self.base_url = self._client.api.base_url

        if server_local_presence_updates:
            if len(self._other_clients) != max(len(self.available_servers) - 1, 0):
                raise ConnectionError("Can't connect to all servers, this can cause missed presence updates.")

            for client in self._other_clients:
                # TODO HERE eventually remove everything not needed except for the presence listening on 
                # all `other_clients` - we don't have to listen for the same broadcast messages 
                # on multiple clients
                pass

            # other_clients can also be an empty list. Then we will only listen
            # for presence update events on
            self.user_manager = MultiListenerUserAddressManager(
                client=self._client,
                presence_listener_clients=self._other_clients,
                displayname_cache=self._displayname_cache,
                address_reachability_changed_callback=noop_reachability,
            )
        else:
            self.user_manager = UserAddressManager(
                client=self._client,
                displayname_cache=self._displayname_cache,
                address_reachability_changed_callback=noop_reachability,
            )

        self.startup_finished = AsyncResult()
        self._rate_limiter = RateLimiter(
            allowed_bytes=MATRIX_RATE_LIMIT_ALLOWED_BYTES,
            reset_interval=MATRIX_RATE_LIMIT_RESET_INTERVAL,
        )


    def _run(self) -> None:  # pylint: disable=method-hidden
        self._start_clients()

        for client in self._all_clients:
            client.start_listener_thread(
                timeout_ms=DEFAULT_TRANSPORT_MATRIX_SYNC_TIMEOUT,
                latency_ms=DEFAULT_TRANSPORT_MATRIX_SYNC_LATENCY,
            )
            # FIXME shutdown others? before assert?
            assert client.sync_worker

        for client in self._all_clients:
            # If any of the sync workers fail, waiting for startup_finished does not
            # make any sense
            client.sync_worker.link_exception(self.startup_finished)

        def set_startup_finished() -> None:
            # This will notify the waiter that the startup finished for all clients (success)
            # Waiting on "client.processed" waits until the next long-polling cycle is conducted
            gevent.wait([client.processed for client in self._all_clients])
            self.startup_finished.set()

        startup_finished_greenlet = gevent.spawn(set_startup_finished)

        try:
            # block until any of the worker finished or raises
            gevent.joinall({client.sync_worker for client in self._all_clients}, count=1, raise_error=True)
        finally:
            # if any worker gets shut down, stop the listener threads of all other clients 
            # as well
            for client in self._all_clients:
                # XXX (ML) call client.stop() on all clients!
                # Before this commit, this was only stopping the listener thread.
                # But here we want to properly stop all clients that were running normally
                # TODO is this the correct way to handle this? Can we call stop() even though
                # the worker of e.g. 1 thread already died?
                client.stop()
            gevent.joinall({startup_finished_greenlet}, raise_error=True, timeout=0)

    @property
    def _all_clients(self):
        return [self._client] + self._other_clients

    def _start_clients(self) -> None:
        # FIXME this could be (somewhat) optimized concurrently
        # (at least the login stage, and then the filter creation /registration stage)
        try:
            self.user_manager.start()

            for client in self._all_clients:
                login(client, signer=LocalSigner(private_key=self.private_key))
        except (MatrixRequestError, ValueError):
            raise ConnectionError("Could not login/register to matrix.")

        try:
            room_alias_prefix = make_room_alias(self.chain_id, self.service_room_suffix)
            server = urlparse(self._client.api.base_url).netloc
            room_alias = f"#{room_alias_prefix}:{server}"
            self._broadcast_room = join_broadcast_room(
                client=self._client, broadcast_room_alias=room_alias
            )
            self.broadcast_room_id = self._broadcast_room.room_id

            for client in self._all_clients:
                sync_filter_id = client.create_sync_filter(rooms=[self._broadcast_room])
                # TODO Can we reuse the serverside filter across clients by setting the same filter-id?
                client.set_sync_filter_id(sync_filter_id)
        except (MatrixRequestError, TransportError):
            raise ConnectionError("Could not join monitoring broadcasting room.")

    def follow_address_presence(self, address: Address, refresh: bool = False) -> None:
        self.user_manager.add_address(address)

        if refresh:
            self.user_manager.populate_userids_for_address(address)
            self.user_manager.track_address_presence(
                address=address, user_ids=self.user_manager.get_userids_for_address(address)
            )

        log.debug(
            "Tracking address",
            address=to_checksum_address(address),
            current_presence=self.user_manager.get_address_reachability(address),
            refresh=refresh,
        )

    def _get_user_from_user_id(self, user_id: str) -> User:
        """Creates an User from an user_id, if none, or fetch a cached User """
        assert self._broadcast_room
        if user_id in self._broadcast_room._members:  # pylint: disable=protected-access
            user: User = self._broadcast_room._members[user_id]  # pylint: disable=protected-access
        else:
            user = self._client.get_user(user_id)

        return user

    def _handle_matrix_sync(self, messages: MatrixSyncMessages) -> bool:
        all_messages: List[Message] = list()
        for room, room_messages in messages:
            # Ignore toDevice messages
            if not room:
                continue

            for text in room_messages:
                all_messages.extend(self._handle_message(room, text))

        log.debug("Incoming messages", messages=all_messages)

        for message in all_messages:
            self.message_received_callback(message)

        return True

    def _handle_message(self, room: Room, message: MatrixMessage) -> List[SignedMessage]:
        """Handle a single Matrix message.

        The matrix message is expected to be a NDJSON, and each entry should be
        a valid JSON encoded Raiden message.
        """
        is_valid_type = (
            message["type"] == "m.room.message" and message["content"]["msgtype"] == "m.text"
        )
        if not is_valid_type:
            return []

        sender_id = message["sender"]
        user = self._get_user_from_user_id(sender_id)
        try:
            self._displayname_cache.warm_users([user])
        # handles the "Could not get 'display_name' for user" case
        except TransportError as ex:
            log.error("Could not warm display cache", peer_user=user.user_id, error=str(ex))
            return []

        peer_address = validate_userid_signature(user)

        if not peer_address:
            log.debug(
                "Message from invalid user displayName signature",
                peer_user=user.user_id,
                room=room,
            )
            return []

        data = message["content"]["body"]
        if not isinstance(data, str):
            log.warning(
                "Received message body not a string",
                peer_user=user.user_id,
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
