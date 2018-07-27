from typing import Dict, Callable


class BlockchainListenerMock:
    """ A class to test Blockchain listener integration. """

    def __init__(self):
        self.confirmed_callbacks: Dict[str, Callable] = {}
        self.unconfirmed_callbacks: Dict[str, Callable] = {}

    def add_confirmed_listener(self, event_name: str, callback: Callable):
        """ Add a callback to listen for confirmed events. """
        self.confirmed_callbacks[event_name] = callback

    def add_unconfirmed_listener(self, event_name: str, callback: Callable):
        """ Add a callback to listen for unconfirmed events. """
        self.unconfirmed_callbacks[event_name] = callback

    # mocking functions
    def emit_event(self, event: Dict, confirmed: bool = True):
        """ Emit a mocked event.

        Args:
            event: A dict containing the event information. This need to contain a key
                'name' which is used to dispatch the event to the right listener.
            confirmed: Whether or not the event is confirmed. """
        assert 'name' in event
        event_name = event['name']

        if confirmed:
            if event_name in self.confirmed_callbacks:
                self.confirmed_callbacks[event_name](event)
        else:
            if event_name in self.unconfirmed_callbacks:
                self.unconfirmed_callbacks[event_name](event)
