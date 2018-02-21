import json
import gevent
import logging

from matrix_client.client import MatrixClient
from monitoring_service.transport import Transport

log = logging.getLogger(__name__)


class MatrixTransport(Transport):
    def __init__(self, homeserver, username, password, matrix_room):
        super().__init__()
        self.homeserver = homeserver
        self.username = username
        self.password = password
        self.room_name = matrix_room
        self.is_running = gevent.event.Event()

    def connect(self):
        self.client = MatrixClient(self.homeserver)
        self.client.login_with_password(self.username, self.password)
        self.client.start_listener_thread()

        self.room = self.client.join_room(self.room_name)

    def get_room_events(self, limit=100):
        f = {"room": {"timeline": {"limit": 100}}}
        result = self.client.api.sync(filter=json.dumps(f))
        room_id = self.room.room_id
        room = result['rooms']['join'][room_id]
        return room['timeline']['events']

    def sync_history(self):
        events = self.get_room_events()
        for event in events:
            self.push_event(event)

    def push_event(self, event):
        for listener in self.room.listeners:
            if listener['event_type'] is None or listener['event_type'] == event['type']:
                listener['callback'](self.room, event)

    def dispatch(self, room, event):
        if event['type'] == "m.room.message":
            if event['content']['msgtype'] == "m.text":
                self.run_message_callbacks(event)
                log.debug("{0}: {1}".format(event['sender'], event['content']['body']))

    def send_message(self, message):
        assert self.transport.room is not None
        self.transport.room.send_text(message)

    def _run(self):
        self.connect()
        self.room.add_listener(lambda room, event: self.dispatch(room, event))
        self.sync_history()
        self.is_running.wait()
