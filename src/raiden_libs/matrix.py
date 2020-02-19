import sys
from datetime import datetime, timedelta
from typing import Callable, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import gevent
import structlog
from eth_utils import decode_hex, to_checksum_address
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
    join_broadcast_room,
    login,
    make_client,
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
from raiden.utils.typing import Address, ChainID

log = structlog.get_logger(__name__)


def noop_reachability(  # pylint: disable=unused-argument
    address: Address, reachability: AddressReachability
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
        private_key: str,
        chain_id: ChainID,
        service_room_suffix: str,
        message_received_callback: Callable[[Message], None],
        servers: Optional[List[str]] = None,
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

        self._client = make_client(
            handle_messages_callback=self._handle_matrix_sync,
            handle_member_join_callback=lambda room: None,
            servers=self.available_servers,
            http_pool_maxsize=4,
            http_retry_timeout=40,
            http_retry_delay=matrix_http_retry_delay,
        )
        self._broadcast_room: Optional[Room] = None
        self._displayname_cache = DisplayNameCache()

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
        self._start_client()

        self._client.start_listener_thread(
            timeout_ms=DEFAULT_TRANSPORT_MATRIX_SYNC_TIMEOUT,
            latency_ms=DEFAULT_TRANSPORT_MATRIX_SYNC_LATENCY,
        )
        assert self._client.sync_worker
        # When the sync worker fails, waiting for startup_finished does not
        # make any sense.
        self._client.sync_worker.link(self.startup_finished)

        def set_startup_finished() -> None:
            self._client.processed.wait()
            self.startup_finished.set()

        startup_finished_greenlet = gevent.spawn(set_startup_finished)
        try:
            self._client.sync_worker.get()
        finally:
            self._client.stop_listener_thread()
            gevent.joinall({startup_finished_greenlet}, raise_error=True, timeout=0)

    def _start_client(self) -> None:
        try:
            self.user_manager.start()

            login(
                self._client, signer=LocalSigner(private_key=decode_hex(self.private_key)),
            )
        except (MatrixRequestError, ValueError):
            raise ConnectionError("Could not login/register to matrix.")

        try:
            room_alias_prefix = make_room_alias(self.chain_id, self.service_room_suffix)
            server = urlparse(self._client.api.base_url).netloc
            room_alias = f"#{room_alias_prefix}:{server}"
            self._broadcast_room = join_broadcast_room(
                client=self._client, broadcast_room_alias=room_alias
            )

            sync_filter_id = self._client.create_sync_filter(rooms=[self._broadcast_room])
            self._client.set_sync_filter_id(sync_filter_id)
        except (MatrixRequestError, TransportError):
            raise ConnectionError("Could not join monitoring broadcasting room.")

    def follow_address_presence(self, address: Address, refresh: bool = False) -> None:
        self.user_manager.add_address(address)

        if refresh:
            self.user_manager.populate_userids_for_address(address)
            self.user_manager.track_address_presence(
                address=address, user_ids=self.user_manager.get_userids_for_address(address),
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
            for text in room_messages:
                all_messages.extend(self._handle_message(room, text))

        log.debug("Incoming messages", messages=all_messages)

        for message in all_messages:
            self.message_received_callback(message)

        return True

    def _handle_message(self, room: Room, message: MatrixMessage) -> List[SignedMessage]:
        """ Handle a single Matrix message.

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
        self._displayname_cache.warm_users([user])
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
