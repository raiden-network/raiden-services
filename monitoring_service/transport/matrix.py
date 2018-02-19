from matrix_client.client import MatrixClient
import json


class MatrixTransport:
    def __init__(self, homeserver, username, password, channel):
        self.homeserver = homeserver
        self.username = username
        self.password = password
        self.channel = channel

    def connect(self):
        self.client = MatrixClient(self.homeserver)
        self.client.login_with_password(self.username, self.password)
        self.client.start_listener_thread()

        self.room = self.client.join_room(self.channel)

    def add_listener(self, handle, event_type=None):
        assert self.room is not None
        self.room.add_listener(handle, event_type)

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
