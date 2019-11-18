import sys
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

import gevent
import structlog
from eth_utils import decode_hex, to_checksum_address
from gevent.event import Event
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
from raiden.network.transport.matrix.client import GMatrixClient, Room
from raiden.network.transport.matrix.utils import (
    AddressReachability,
    DisplayNameCache,
    UserAddressManager,
    login,
    make_client,
    make_room_alias,
    validate_userid_signature,
)
from raiden.network.transport.utils import timeout_exponential_backoff
from raiden.settings import (
    DEFAULT_MATRIX_KNOWN_SERVERS,
    DEFAULT_TRANSPORT_MATRIX_RETRY_INTERVAL,
    DEFAULT_TRANSPORT_RETRIES_BEFORE_BACKOFF,
)
from raiden.storage.serialization.serializer import MessageSerializer
from raiden.utils.cli import get_matrix_servers
from raiden.utils.signer import LocalSigner
from raiden.utils.typing import Address, ChainID

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
        int(DEFAULT_TRANSPORT_MATRIX_RETRY_INTERVAL / 5),
        int(DEFAULT_TRANSPORT_MATRIX_RETRY_INTERVAL),
    )


class MatrixListener(gevent.Greenlet):
    # pylint: disable=too-many-instance-attributes
    def __init__(
        self,
        private_key: str,
        chain_id: ChainID,
        service_room_suffix: str,
        message_received_callback: Callable[[Message], None],
        address_reachability_changed_callback: Callable[
            [Address, AddressReachability], None
        ] = None,
        servers: List[str] = None,
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

        self.client = make_client(
            servers=self.available_servers,
            http_pool_maxsize=4,
            http_retry_timeout=40,
            http_retry_delay=matrix_http_retry_delay,
        )
        self.broadcast_rooms: List[Room] = []
        self._displayname_cache = DisplayNameCache()
        self._user_manager: Optional[UserAddressManager] = None

        if address_reachability_changed_callback is not None:
            self._user_manager = UserAddressManager(
                client=self.client,
                displayname_cache=self._displayname_cache,
                address_reachability_changed_callback=address_reachability_changed_callback,
            )

        self.startup_finished = Event()
        self.rate_limiter = RateLimiter(
            allowed_bytes=MATRIX_RATE_LIMIT_ALLOWED_BYTES,
            reset_interval=MATRIX_RATE_LIMIT_RESET_INTERVAL,
        )

    def listen_forever(self) -> None:
        self.startup_finished.wait()
        self.client.listen_forever()

    def _run(self) -> None:  # pylint: disable=method-hidden
        self._start_client()

        self.client.start_listener_thread()
        assert self.client.sync_thread
        self.client.sync_thread.get()

    def stop(self) -> None:
        if self._user_manager:
            self._user_manager.stop()
        self.client.stop_listener_thread()

    def _start_client(self) -> None:
        try:
            if self._user_manager:
                self._user_manager.start()

            login(self.client, signer=LocalSigner(private_key=decode_hex(self.private_key)))
        except (MatrixRequestError, ValueError):
            raise ConnectionError("Could not login/register to matrix.")

        try:
            self.join_global_rooms(client=self.client, available_servers=self.available_servers)
        except (MatrixRequestError, TransportError):
            raise ConnectionError("Could not join monitoring broadcasting room.")

        # Add listener for global rooms
        for broadcast_room in self.broadcast_rooms:
            broadcast_room.add_listener(self._handle_message, "m.room.message")

        # Signal that startup is finished
        self.startup_finished.set()

    def follow_address_presence(self, address: Address, refresh: bool = False) -> None:
        if self._user_manager:
            self._user_manager.add_address(address)

            if refresh:
                self._user_manager.populate_userids_for_address(address)
                self._user_manager.track_address_presence(
                    address=address, user_ids=self._user_manager.get_userids_for_address(address)
                )

            log.debug(
                "Tracking address",
                address=to_checksum_address(address),
                current_presence=self._user_manager.get_address_reachability(address),
                refresh=refresh,
            )

    def _get_user_from_user_id(self, user_id: str) -> User:
        """Creates an User from an user_id, if none, or fetch a cached User """
        for broadcast_room in self.broadcast_rooms:
            if user_id in broadcast_room._members:  # pylint: disable=protected-access
                user: User = broadcast_room._members[user_id]  # pylint: disable=protected-access
                break
        else:
            user = self.client.get_user(user_id)

        return user

    def _handle_message(self, room: Any, event: dict) -> bool:
        """ Handle text messages sent to listening rooms """
        if event["type"] != "m.room.message" or event["content"]["msgtype"] != "m.text":
            # Ignore non-messages and non-text messages
            return False

        sender_id = event["sender"]
        user = self._get_user_from_user_id(sender_id)
        self._displayname_cache.warm_users([user])
        peer_address = validate_userid_signature(user)

        if not peer_address:
            log.debug(
                "Message from invalid user displayName signature",
                peer_user=user.user_id,
                room=room,
            )
            return False

        data = event["content"]["body"]
        if not isinstance(data, str):
            log.warning(
                "Received message body not a string",
                peer_user=user.user_id,
                peer_address=to_checksum_address(peer_address),
                room=room,
            )
            return False

        messages = deserialize_messages(data, peer_address, self.rate_limiter)
        if not messages:
            return False

        for message in messages:
            assert message.sender, "Message has no sender"
            self.message_received_callback(message)

        return True

    def join_global_rooms(
        self, client: GMatrixClient, available_servers: Sequence[str] = ()
    ) -> None:
        """Join or create a global public room with given name on all available servers.
        If global rooms are not found, create a public room with the name on each server.

        Params:
            client: matrix-python-sdk client instance
            servers: optional: sequence of known/available servers to try to find the room in
        """
        suffix = self.service_room_suffix
        room_alias_prefix = make_room_alias(self.chain_id, suffix)

        parsed_servers = [
            urlparse(s).netloc for s in available_servers if urlparse(s).netloc not in {None, ""}
        ]

        for server in parsed_servers:
            room_alias_full = f"#{room_alias_prefix}:{server}"
            log.debug(f"Trying to join {suffix} room", room_alias_full=room_alias_full)
            try:
                broadcast_room = client.join_room(room_alias_full)
                log.debug(f"Joined {suffix} room", room=broadcast_room)
                self.broadcast_rooms.append(broadcast_room)
            except MatrixRequestError as ex:
                if ex.code != 404:
                    log.debug(
                        f"Could not join {suffix} room, trying to create one",
                        room_alias_full=room_alias_full,
                    )
                    try:
                        broadcast_room = client.create_room(room_alias_full, is_public=True)
                        log.debug(f"Created {suffix} room", room=broadcast_room)
                        self.broadcast_rooms.append(broadcast_room)
                    except MatrixRequestError:
                        log.debug(
                            f"Could neither join nor create a {suffix} room",
                            room_alias_full=room_alias_full,
                        )
                        raise TransportError(f"Could neither join nor create a {suffix} room")

                else:
                    log.debug(
                        f"Could not join {suffix} room",
                        room_alias_full=room_alias_full,
                        _exception=ex,
                    )
                    raise
