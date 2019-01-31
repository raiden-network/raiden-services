import json
import logging

import gevent
import requests
from matrix_client.client import MatrixClient
from matrix_client.errors import MatrixHttpLibError

from raiden_libs.transport import Transport

log = logging.getLogger(__name__)


class MatrixTransport(Transport):
    def __init__(self, homeserver, username, password, matrix_room):
        super().__init__()
        self.homeserver = homeserver
        self.username = username
        self.password = password
        self.room_name = matrix_room
        self.is_running = gevent.event.Event()
        self.do_reconnect = gevent.event.AsyncResult()
        self.retry_timeout = 5
        self.client = None

    def matrix_exception_handler(self, e):
        """Called whenever an exception occurs in matrix client thread.

            Any exception other than MatrixHttpLibError will be sent to parent hub,
             terminating the program.
        """
        if isinstance(e, MatrixHttpLibError):
            log.warning(str(e))
            self.do_reconnect.set(100)
            raise e
        gevent.get_hub().parent.throw(e)

    def connect(self):
        """Connects to a matrix homeserver and initializes the client class"""
        if self.client is not None:
            self.client.logout()
            self.client = None
        self.client = MatrixClient(self.homeserver)
        self.client.login_with_password(self.username, self.password)
        self.room = self.client.join_room(self.room_name)
        self.client.start_listener_thread(
            exception_handler=lambda e: self.matrix_exception_handler(e),
        )

    def get_room_events(self, limit=100):
        """Get past messages in the broadcast room, up to the @limit"""
        sync_filter = {"room": {"timeline": {"limit": limit}}}
        result = self.client.api.sync(filter=json.dumps(sync_filter))
        room_id = self.room.room_id
        room = result['rooms']['join'][room_id]
        return room['timeline']['events']

    def sync_history(self):
        """Calls event callback for all events retrieved from the broadcast room history"""
        events = self.get_room_events()
        for event in events:
            self.push_event(event)

    def push_event(self, event):
        """Calls a registered event callback"""
        for listener in self.room.listeners:
            if listener['event_type'] is None or listener['event_type'] == event['type']:
                listener['callback'](self.room, event)

    def dispatch(self, room, event):
        if event['type'] == "m.room.message":
            if event['content']['msgtype'] == "m.text":
                self.run_message_callbacks(event['content']['body'])
                log.debug("{0}: {1}".format(event['sender'], event['content']['body']))

    def transmit_data(self, message: str, target_node: str = None):
        # TODO: fix sending to certain receiver
        assert self.room is not None
        self.room.send_text(message)

    def _run(self):
        """Gevent loop. The Matrix connection is restored automatically on error."""
        while self.is_running.is_set() is False:
            try:
                self.connect()
                self.room.add_listener(lambda room, event: self.dispatch(room, event))
                self.sync_history()
                self.do_reconnect.wait()
                if self.do_reconnect.get() == 100:
                    gevent.sleep(self.retry_timeout)
                    continue
            except (requests.exceptions.ConnectionError, MatrixHttpLibError) as e:
                log.warn(
                    "Connection to %s failed. Retrying in %d seconds (%s)" %
                    (
                        self.homeserver,
                        self.retry_timeout,
                        str(e),
                    ),
                )
                gevent.sleep(self.retry_timeout)
