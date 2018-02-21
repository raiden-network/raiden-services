import gevent
import gevent.event
import logging
from monitoring_service.constants import EVENT_CHANNEL_CLOSE, EVENT_CHANNEL_CREATE

log = logging.getLogger(__name__)


class BlockchainMonitor(gevent.Greenlet):
    def __init__(self):
        super().__init__()
        self.is_running = gevent.event.Event()
        self.event_handlers = {
            EVENT_CHANNEL_CLOSE: [],
            EVENT_CHANNEL_CREATE: []
        }

    def _run(self):
        while self.is_running.is_set():
            self.poll_blockchain()

    def register_handler(self, event, callback):
        self.event_handlers[event].append(callback)

    def poll_blockchain(self):
        pass

    def stop(self):
        self.is_running.clear()

    def handle_event(self, event):
        handlers = self.event_handlers.get(event['name'], None)
        if handlers is None:
            log.warning('unhandled event type: %s' % str(event))
            return
        [x(event) for x in handlers]
