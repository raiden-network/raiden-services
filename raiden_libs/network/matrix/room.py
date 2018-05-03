from matrix_client.room import Room as MatrixRoom

from .utils import geventify_callback


class Room(MatrixRoom):
    """ Matrix `Room` subclass that invokes listener callbacks in separate greenlets """
    def add_listener(self, callback, event_type=None):
        return super().add_listener(geventify_callback(callback), event_type)

    def add_ephemeral_listener(self, callback, event_type=None):
        return super().add_ephemeral_listener(geventify_callback(callback), event_type)

    def add_state_listener(self, callback, event_type=None):
        super().add_state_listener(geventify_callback(callback), event_type)
