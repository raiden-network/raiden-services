import json
import sys
from typing import Any, Callable, Dict, Iterable, List, Tuple, Union

import gevent
import structlog
from eth_utils import decode_hex, to_checksum_address
from matrix_client.errors import MatrixRequestError
from matrix_client.user import User

from raiden.constants import Environment
from raiden.exceptions import InvalidProtocolMessage, TransportError
from raiden.messages import Message, RequestMonitoring, SignedMessage, UpdatePFS
from raiden.network.transport.matrix.client import GMatrixClient, Room
from raiden.network.transport.matrix.utils import (
    join_global_room,
    login_or_register,
    make_client,
    make_room_alias,
    validate_userid_signature,
)
from raiden.network.transport.udp import udp_utils
from raiden.settings import (
    DEFAULT_MATRIX_KNOWN_SERVERS,
    DEFAULT_TRANSPORT_MATRIX_RETRY_INTERVAL,
    DEFAULT_TRANSPORT_RETRIES_BEFORE_BACKOFF,
)
from raiden.utils.cli import get_matrix_servers
from raiden.utils.signer import LocalSigner
from raiden.utils.typing import ChainID

log = structlog.get_logger(__name__)


SERVICE_MESSAGES: Tuple = (UpdatePFS, RequestMonitoring)
CLASSNAME_TO_CLASS: Dict[str, Message] = {klass.__name__: klass for klass in SERVICE_MESSAGES}


def message_from_dict(data: dict) -> Message:
    try:
        klass: Message = CLASSNAME_TO_CLASS[data['type']]
    except KeyError:
        if 'type' in data:
            raise InvalidProtocolMessage(
                'Invalid message type (data["type"] = {})'.format(data['type'])
            ) from None
        raise InvalidProtocolMessage('Invalid message data. Can not find the data type') from None

    return klass.from_dict(data)


class MatrixListener(gevent.Greenlet):
    def __init__(
        self, private_key: str, chain_id: ChainID, callback: Callable, service_room_suffix: str
    ) -> None:
        super().__init__()

        self.private_key = private_key
        self.chain_id = chain_id
        self.callback = callback

        try:
            self.client, self.monitoring_room = self.setup_matrix(service_room_suffix)
            self.monitoring_room.add_listener(self._handle_message, 'm.room.message')
        except ConnectionError as e:
            log.critical('Could not connect to broadcasting system.', exc=e)
            sys.exit(1)

    def listen_forever(self) -> None:
        self.client.listen_forever()

    def _run(self) -> None:  # pylint: disable=method-hidden
        self.client.start_listener_thread()
        self.client.sync_thread.get()

    def stop(self) -> None:
        self.client.stop_listener_thread()

    def setup_matrix(self, service_room_suffix: str) -> Tuple[GMatrixClient, Room]:
        available_servers_url = DEFAULT_MATRIX_KNOWN_SERVERS[Environment.DEVELOPMENT]
        available_servers = get_matrix_servers(available_servers_url)

        def _http_retry_delay() -> Iterable[float]:
            # below constants are defined in raiden.app.App.DEFAULT_CONFIG
            return udp_utils.timeout_exponential_backoff(
                DEFAULT_TRANSPORT_RETRIES_BEFORE_BACKOFF,
                int(DEFAULT_TRANSPORT_MATRIX_RETRY_INTERVAL / 5),
                int(DEFAULT_TRANSPORT_MATRIX_RETRY_INTERVAL),
            )

        client = make_client(
            servers=available_servers,
            http_pool_maxsize=4,
            http_retry_timeout=40,
            http_retry_delay=_http_retry_delay,
        )

        try:
            login_or_register(client, signer=LocalSigner(private_key=decode_hex(self.private_key)))
        except (MatrixRequestError, ValueError):
            raise ConnectionError('Could not login/register to matrix.')

        try:
            room_name = make_room_alias(self.chain_id, service_room_suffix)
            monitoring_room = join_global_room(
                client=client, name=room_name, servers=available_servers
            )
        except (MatrixRequestError, TransportError):
            raise ConnectionError('Could not join monitoring broadcasting room.')

        return client, monitoring_room

    def _get_user(self, user: Union[User, str]) -> User:
        """Creates an User from an user_id, if none, or fetch a cached User """
        user_id: str = getattr(user, 'user_id', user)
        if self.monitoring_room and user_id in self.monitoring_room._members:
            duser: User = self.monitoring_room._members[user_id]

            # if handed a User instance with displayname set, update the discovery room cache
            if getattr(user, 'displayname', None):
                assert isinstance(user, User)
                duser.displayname = user.displayname
            user = duser
        elif not isinstance(user, User):
            user = self.client.get_user(user_id)

        return user

    def _handle_message(self, room: Any, event: dict) -> bool:
        """ Handle text messages sent to listening rooms """
        if event['type'] != 'm.room.message' or event['content']['msgtype'] != 'm.text':
            # Ignore non-messages and non-text messages
            return False

        sender_id = event['sender']
        user = self._get_user(sender_id)
        peer_address = validate_userid_signature(user)

        if not peer_address:
            log.debug(
                'Message from invalid user displayName signature',
                peer_user=user.user_id,
                room=room,
            )
            return False

        data = event['content']['body']
        if not isinstance(data, str):
            log.warning(
                'Received message body not a string',
                peer_user=user.user_id,
                peer_address=to_checksum_address(peer_address),
                room=room,
            )
            return False

        messages: List[SignedMessage] = list()

        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue

            logger = log.bind(peer_address=to_checksum_address(peer_address))
            try:
                message_dict = json.loads(line)
                message = message_from_dict(message_dict)
            except (UnicodeDecodeError, json.JSONDecodeError) as ex:
                logger.warning("Can't parse message data JSON", message_data=line, _exc=ex)
                continue
            except (InvalidProtocolMessage, KeyError) as ex:
                logger.warning(
                    "Message data JSON is not a valid message", message_data=line, _exc=ex
                )
                continue

            if not isinstance(message, SignedMessage):
                logger.warning('Received invalid message', message=message)
                continue
            elif message.sender != peer_address:
                logger.warning(
                    'Message not signed by sender!', message=message, signer=message.sender
                )
                continue
            messages.append(message)

        if not messages:
            return False

        for message in messages:
            log.debug(
                'Message received', message=message, sender=to_checksum_address(message.sender)
            )
            self.callback(message)

        return True
