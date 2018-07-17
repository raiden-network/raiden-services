import logging
from typing import List, Callable, Dict, Any
from urllib.parse import quote
from collections import defaultdict

import gevent
from gevent.lock import Semaphore
from matrix_client.client import CACHE, MatrixClient
from matrix_client.errors import MatrixRequestError
from matrix_client.user import User

from .room import Room
from .utils import geventify_callback


logger = logging.getLogger(__name__)


class GMatrixClient(MatrixClient):
    """ Gevent-compliant MatrixClient subclass """

    def __init__(
            self,
            base_url: str,
            token: str = None,
            user_id: str = None,
            valid_cert_check: bool = True,
            sync_filter_limit: int = 20,
            cache_level: CACHE = CACHE.ALL,
    ) -> None:
        # dict of 'type': 'content' key/value pairs
        self.account_data: Dict[str, Dict[str, Any]] = dict()

        super().__init__(
            base_url,
            token,
            user_id,
            valid_cert_check,
            sync_filter_limit,
            cache_level,
        )
        self.should_listen = False
        self.sync_thread = None
        self.greenlets: List[gevent.Greenlet] = list()
        self.api.session.headers.update({'Connection': 'close'})

        # locks each account_data's 'type_' key until it's _sync'ed
        self.account_data_locks: Dict[str, Semaphore] = defaultdict(Semaphore)

    def geventify(self, callback):
        return geventify_callback(
            callback,
            on_spawn=lambda spawned: self.greenlets.append(spawned),
        )

    def listen_forever(
        self,
        timeout_ms: int = 30000,
        exception_handler: Callable = None,
        bad_sync_timeout: int = 5,
    ):
        """
        Keep listening for events forever.
        Args:
            timeout_ms: How long to poll the Home Server for before retrying.
            exception_handler: Optional exception handler function which can
                be used to handle exceptions in the caller thread.
            bad_sync_timeout: Base time to wait after an error before retrying.
                Will be increased according to exponential backoff.
        """
        _bad_sync_timeout = bad_sync_timeout
        self.should_listen = True
        while self.should_listen:
            try:
                self._sync(timeout_ms)
                _bad_sync_timeout = bad_sync_timeout
            except MatrixRequestError as e:
                logger.warning('A MatrixRequestError occured during sync.')
                if e.code >= 500:
                    logger.warning(
                        'Problem occured serverside. Waiting %i seconds',
                        _bad_sync_timeout,
                    )
                    gevent.sleep(_bad_sync_timeout)
                    _bad_sync_timeout = min(_bad_sync_timeout * 2, self.bad_sync_timeout_limit)
                else:
                    raise
            except Exception as e:
                logger.exception('Exception thrown during sync')
                if exception_handler is not None:
                    exception_handler(e)
                else:
                    raise

    def start_listener_thread(self, timeout_ms: int = 30000, exception_handler: Callable = None):
        """
        Start a listener greenlet to listen for events in the background.
        Args:
            timeout_ms: How long to poll the Home Server for before retrying.
            exception_handler: Optional exception handler function which can
                be used to handle exceptions in the caller thread.
        """
        self.should_listen = True
        self.sync_thread = gevent.spawn(self.listen_forever, timeout_ms, exception_handler)

    def search_user_directory(self, term: str) -> List[User]:
        """
        Search user directory for a given term, returning a list of users
        Args:
            term: term to be searched for
        Returns:
            user_list: list of users returned by server-side search
        """
        response = self.api._send(
            'POST',
            '/user_directory/search',
            {
                'search_term': term,
            },
        )
        try:
            return [
                User(self.api, _user['user_id'], _user['display_name'])
                for _user in response['results']
            ]
        except KeyError:
            return []

    def search_room_directory(self, filter_term: str = None, limit: int = 10) -> List[Room]:
        filter_options: dict = {}
        if filter_term:
            filter_options = {
                'filter': {
                    'generic_search_term': filter_term,
                },
            }

        response = self.api._send(
            'POST',
            '/publicRooms',
            {
                'limit': limit,
                **filter_options,
            },
        )
        rooms = []
        for room_info in response['chunk']:
            room = Room(self, room_info['room_id'])
            room.canonical_alias = room_info.get('canonical_alias')
            rooms.append(room)
        return rooms

    def modify_presence_list(
        self,
        add_user_ids: List[str] = None,
        remove_user_ids: List[str] = None,
    ):
        if add_user_ids is None:
            add_user_ids = []
        if remove_user_ids is None:
            remove_user_ids = []
        return self.api._send(
            'POST',
            f'/presence/list/{quote(self.user_id)}',
            {
                'invite': add_user_ids,
                'drop': remove_user_ids,
            },
        )

    def get_presence_list(self) -> List[dict]:
        return self.api._send(
            'GET',
            f'/presence/list/{quote(self.user_id)}',
        )

    def set_presence_state(self, state: str):
        return self.api._send(
            'PUT',
            f'/presence/{quote(self.user_id)}/status',
            {
                'presence': state,
            },
        )

    def typing(self, room: Room, timeout: int=5000):
        """
        Send typing event directly to api

        Args:
            room: room to send typing event to
            timeout: timeout for the event, in ms
        """
        path = f'/rooms/{quote(room.room_id)}/typing/{quote(self.user_id)}'
        return self.api._send('PUT', path, {'typing': True, 'timeout': timeout})

    def add_invite_listener(self, callback: Callable):
        super().add_invite_listener(self.geventify(callback))

    def add_leave_listener(self, callback: Callable):
        super().add_leave_listener(self.geventify(callback))

    def add_presence_listener(self, callback: Callable):
        return super().add_presence_listener(self.geventify(callback))

    def add_listener(self, callback: Callable, event_type: str = None):
        return super().add_listener(self.geventify(callback), event_type)

    def add_ephemeral_listener(self, callback: Callable, event_type: str = None):
        return super().add_ephemeral_listener(self.geventify(callback), event_type)

    def _mkroom(self, room_id: str) -> Room:
        """ Uses a geventified Room subclass """
        if room_id not in self.rooms:
            self.rooms[room_id] = Room(self, room_id)
        room = self.rooms[room_id]
        if not room.canonical_alias:
            room.update_aliases()
        return room

    def join_and_logout(self, greenlets=None, timeout=None):
        all_greenlets = self.greenlets + (greenlets or list())
        finished = gevent.wait(all_greenlets, timeout)
        self.logout()

        if len(finished) < len(all_greenlets):
            raise RuntimeError(
                f'Timeout ({timeout} seconds). Logged out despite unjoined greenlets.',
            )

    def get_user_presence(self, user_id: str) -> str:
        return self.api._send('GET', f'/presence/{quote(user_id)}/status').get('presence')

    def _sync(self, timeout_ms=30000):
        """ Copy-pasta from MatrixClient, but add 'account_data' support to /sync """
        response = self.api.sync(self.sync_token, timeout_ms, filter=self.sync_filter)
        self.sync_token = response["next_batch"]

        for presence_update in response['presence']['events']:
            for callback in self.presence_listeners.values():
                callback(presence_update)

        for room_id, invite_room in response['rooms']['invite'].items():
            for listener in self.invite_listeners:
                listener(room_id, invite_room['invite_state'])

        for room_id, left_room in response['rooms']['leave'].items():
            for listener in self.left_listeners:
                listener(room_id, left_room)
            if room_id in self.rooms:
                del self.rooms[room_id]

        for room_id, sync_room in response['rooms']['join'].items():
            if room_id not in self.rooms:
                self._mkroom(room_id)
            room = self.rooms[room_id]
            # TODO: the rest of this for loop should be in room object method
            room.prev_batch = sync_room["timeline"]["prev_batch"]

            for event in sync_room["state"]["events"]:
                event['room_id'] = room_id
                room._process_state_event(event)

            for event in sync_room["timeline"]["events"]:
                event['room_id'] = room_id
                room._put_event(event)

                # TODO: global listeners can still exist but work by each
                # room.listeners[uuid] having reference to global listener

                # Dispatch for client (global) listeners
                for listener in self.listeners:
                    if (
                        listener['event_type'] is None or
                        listener['event_type'] == event['type']
                    ):
                        listener['callback'](event)

            for event in sync_room['ephemeral']['events']:
                event['room_id'] = room_id
                room._put_ephemeral_event(event)

                for listener in self.ephemeral_listeners:
                    if (
                        listener['event_type'] is None or
                        listener['event_type'] == event['type']
                    ):
                        listener['callback'](event)

            for event in sync_room['account_data']['events']:
                lock = room.account_data_locks.get(event['type'])
                if lock and lock.locked():
                    # this is our own echo, we already updated the local data
                    lock.release()
                else:
                    room.account_data[event['type']] = event['content']

        for event in response['account_data']['events']:
            lock = self.account_data_locks.get(event['type'])
            if lock and lock.locked():
                # this is our own echo, we already updated the local data
                lock.release()
            else:
                self.account_data[event['type']] = event['content']

    def set_account_data(self, type_: str, content: Dict[str, Any]) -> dict:
        """ Use this to set a key: value pair in account_data to keep it synced on server

        PS: take care of setting only an updated data, or you may replace data that
        just came from the server
        """
        self.account_data[type_] = content
        self.account_data_locks[type_].acquire()
        return self.api.set_account_data(quote(self.user_id), quote(type_), content)
