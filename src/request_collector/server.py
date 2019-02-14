import json
import sys
import traceback
from typing import Iterable, List, Tuple

import gevent
import structlog
from eth_utils import decode_hex, to_checksum_address
from matrix_client.errors import MatrixRequestError

from monitoring_service.database import SharedDatabase
from monitoring_service.states import MonitorRequest
from raiden.constants import MONITORING_BROADCASTING_ROOM, Environment
from raiden.exceptions import InvalidProtocolMessage, TransportError
from raiden.messages import RequestMonitoring, SignedMessage, from_dict as message_from_dict
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
from raiden_libs.exceptions import InvalidSignature
from raiden_libs.gevent_error_handler import register_error_handler

log = structlog.get_logger(__name__)


def error_handler(_context, exc_info):
    log.critical("Unhandled exception terminating the program")
    traceback.print_exception(
        etype=exc_info[0],
        value=exc_info[1],
        tb=exc_info[2],
    )
    sys.exit()


def setup_matrix(private_key: str, chain_id: int) -> Tuple[GMatrixClient, Room]:
    available_servers_url = DEFAULT_MATRIX_KNOWN_SERVERS[Environment.DEVELOPMENT]
    available_servers = get_matrix_servers(available_servers_url)

    def _http_retry_delay() -> Iterable[float]:
        # below constants are defined in raiden.app.App.DEFAULT_CONFIG
        return udp_utils.timeout_exponential_backoff(
            DEFAULT_TRANSPORT_RETRIES_BEFORE_BACKOFF,
            DEFAULT_TRANSPORT_MATRIX_RETRY_INTERVAL / 5,
            DEFAULT_TRANSPORT_MATRIX_RETRY_INTERVAL,
        )

    client = make_client(
        servers=available_servers,
        http_pool_maxsize=4,
        http_retry_timeout=40,
        http_retry_delay=_http_retry_delay,
    )

    try:
        login_or_register(client, signer=LocalSigner(private_key=decode_hex(private_key)))
    except MatrixRequestError:
        raise ConnectionError('Could not login/register to matrix.')
    except ValueError:
        raise ConnectionError('Could not login/register to matrix.')

    try:
        room_name = make_room_alias(chain_id, MONITORING_BROADCASTING_ROOM)
        monitoring_room = join_global_room(
            client=client,
            name=room_name,
            servers=available_servers,
        )
    except MatrixRequestError:
        raise ConnectionError('Could not join monitoring broadcasting room.')
    except TransportError:
        raise ConnectionError('Could not join monitoring broadcasting room.')

    return client, monitoring_room


class RequestCollector(gevent.Greenlet):
    def __init__(
        self,
        private_key: str,
        state_db: SharedDatabase,
    ):
        super().__init__()

        self.private_key = private_key
        self.state_db = state_db

        self.stop_event = gevent.event.Event()
        self.task_list: List[gevent.Greenlet] = []

        state = self.state_db.load_state(0)
        try:
            self.client, self.monitoring_room = setup_matrix(
                private_key=self.private_key,
                chain_id=state.blockchain_state.chain_id,
            )
            self.monitoring_room.add_listener(self._handle_message, 'm.room.message')
        except ConnectionError as e:
            log.critical(
                'Could not connect to broadcasting system.',
                exc=e,
            )
            sys.exit(1)

    def _run(self):
        register_error_handler(error_handler)

        # this loop will wait until spawned greenlets complete
        while self.stop_event.is_set() is False:
            tasks = gevent.wait(self.task_list, timeout=5, count=1)
            if len(tasks) == 0:
                gevent.sleep(1)
                continue
            task = tasks[0]
            log.info('%s completed (%s)' % (task, task.value))
            self.task_list.remove(task)

    def stop(self):
        self.stop_event.set()

    def _handle_message(self, room, event) -> bool:
        """ Handle text messages sent to listening rooms """
        if (
                event['type'] != 'm.room.message' or
                event['content']['msgtype'] != 'm.text' or
                self.stop_event.ready()
        ):
            # Ignore non-messages and non-text messages
            return False

        sender_id = event['sender']

        user = self.client.get_user(sender_id)
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
            try:
                message_dict = json.loads(line)
                message = message_from_dict(message_dict)
            except (UnicodeDecodeError, json.JSONDecodeError) as ex:
                log.warning(
                    "Can't parse message data JSON",
                    message_data=line,
                    peer_address=to_checksum_address(peer_address),
                    _exc=ex,
                )
                continue
            except InvalidProtocolMessage as ex:
                log.warning(
                    "Message data JSON are not a valid message",
                    message_data=line,
                    peer_address=to_checksum_address(peer_address),
                    _exc=ex,
                )
                continue
            if not isinstance(message, SignedMessage):
                log.warning(
                    'Received invalid message',
                    message=message,
                )
                continue
            elif message.sender != peer_address:
                log.warning(
                    'Message not signed by sender!',
                    message=message,
                    signer=message.sender,
                    peer_address=peer_address,
                )
                continue
            messages.append(message)

        if not messages:
            return False

        for message in messages:
            self._receive_message(message)

        return True

    def _receive_message(self, message: SignedMessage):
        log.debug(
            'Message received',
            message=message,
            sender=to_checksum_address(message.sender),
        )

        if isinstance(message, RequestMonitoring):
            self.on_monitor_request(message)
        else:
            log.info('Ignoring unknown message type')

    def on_monitor_request(
        self,
        request_monitoring: RequestMonitoring,
    ):
        """Called whenever a monitor proof message is received.
        This will spawn a greenlet and store its reference in an internal list.
        Return value of the greenlet is then checked in the main loop."""
        assert isinstance(request_monitoring, RequestMonitoring)

        try:
            monitor_request = MonitorRequest(
                channel_identifier=request_monitoring.balance_proof.channel_identifier,
                token_network_address=request_monitoring.balance_proof.token_network_address,
                chain_id=request_monitoring.balance_proof.chain_id,
                balance_hash=request_monitoring.balance_proof.balance_hash.hex(),
                nonce=request_monitoring.balance_proof.nonce,
                additional_hash=request_monitoring.balance_proof.additional_hash.hex(),
                closing_signature=request_monitoring.balance_proof.signature.hex(),
                non_closing_signature=request_monitoring.non_closing_signature.hex(),
                reward_amount=request_monitoring.reward_amount,
                reward_proof_signature=request_monitoring.signature.hex(),
            )
            self.state_db.upsert_monitor_request(monitor_request)
        except InvalidSignature:
            log.info('Ignore MR with invalid signature {}'.format(request_monitoring))

    def start_task(self, task: gevent.Greenlet):
        task.start()
        self.task_list.append(task)

    def wait_tasks(self):
        """Wait until all internal tasks are finished"""
        while True:
            if len(self.task_list) == 0:
                return
            gevent.sleep(1)
