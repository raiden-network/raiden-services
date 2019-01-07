import json
import logging
import random

import gevent
import requests

from raiden_contracts.constants import ChannelEvent
from monitoring_service.tools.random_channel import RandomChannelDB

log = logging.getLogger(__name__)

API_PATH = '/api/1/events'


class EventGenerator(gevent.Greenlet):
    def __init__(self, host: str, seed: int) -> None:
        super().__init__()
        self.db = RandomChannelDB(seed)
        self.uri = host + API_PATH
        self.headers = {'Content-Type': 'application/json'}
        self.is_running = gevent.event.Event()

    def create_channel(self):
        channel_data = self.db.new_channel()
        self.put_event(
            {
                'name': ChannelEvent.OPENED,
                'data': channel_data
            }
        )

    def put_event(self, event):
        while self.is_running.is_set():
            try:
                requests.put(self.uri, data=json.dumps(event), headers=self.headers)
            except requests.exceptions.ConnectionError as e:
                log.warn("Can't POST to %s: %s" % (self.uri, str(e)))
            finally:
                return
            gevent.sleep(1)

    def delete_channel(self):
        if len(self.db.channel_db) == 0:
            return {}
        channel = random.choice(self.db.channel_db)
        self.db.channel_db.remove(channel)
        self.put_event(
            {
                'name': ChannelEvent.CLOSED,
                'data': channel
            }
        )

    def stop(self):
        self.is_running.clear()

    def _run(self):
        self.is_running.set()
        while self.is_running.is_set():
            if random.randint(0, 1) == 0:
                self.create_channel()
            else:
                self.delete_channel()
            gevent.sleep(random.random() * 5)
