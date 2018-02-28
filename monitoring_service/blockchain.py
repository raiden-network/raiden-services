import gevent
import gevent.event
import logging
import requests
from monitoring_service.constants import (
    EVENT_CHANNEL_CLOSE,
    EVENT_CHANNEL_SETTLED,
    EVENT_TRANSFER_UPDATED
)
from monitoring_service.contract_manager import CONTRACT_MANAGER
from monitoring_service.utils import make_filter, decode_contract_call

log = logging.getLogger(__name__)


class BlockchainMonitor(gevent.Greenlet):
    def __init__(self, web3):
        super().__init__()
        self.is_running = gevent.event.Event()
        self.is_running.set()
        self.event_handlers = {
            EVENT_CHANNEL_CLOSE: [],
            EVENT_CHANNEL_SETTLED: [],
            EVENT_TRANSFER_UPDATED: []
        }
        self.web3 = web3
        self.poll_interval = 5
        self.event_filters = None

    def make_filters(self):
        ret = []
        for event_name in self.event_handlers.keys():
            abi = CONTRACT_MANAGER.get_event_abi('NettingChannelContract', event_name)
            assert abi is not None
            ret.append(make_filter(self.web3, abi[0]))
        return ret

    def _run(self):
        while self.is_running.is_set():
            try:
                if self.event_filters is None:
                    self.event_filters = self.make_filters()
                self.poll_blockchain()
            except requests.exceptions.ConnectionError as e:
                endpoint = self.web3.providers[0].endpoint_uri
                log.warning(
                    'Ethereum node (%s) refused connection. Retrying in %d seconds.' %
                    (endpoint, self.poll_interval)
                )
                self.event_filters = None
                gevent.sleep(self.poll_interval)
        self.uninstall_filters()

    def uninstall_filters(self):
        if self.event_filters is None:
            return
        [self.web3.uninstallFilter(f.filter_id)
         for f in self.event_filters]
        self.event_filters = None

    def register_handler(self, event, callback):
        self.event_handlers[event].append(callback)

    def poll_blockchain(self):
        for f in self.event_filters:
            events = f.get_new_entries()
            [self.handle_event(ev) for ev in events]
        gevent.sleep(self.poll_interval)

    def stop(self):
        self.is_running.clear()

    def handle_event(self, event):
        tx = self.web3.eth.getTransaction(event['transactionHash'])
        abi = CONTRACT_MANAGER.get_contract_abi('NettingChannelContract')
        s = decode_contract_call(abi['abi'], tx['data'])
        assert s is not None
        handlers = self.event_handlers.get(event['event'], None)
        log.info(event)
        if handlers is None:
            log.warning('unhandled event type: %s' % str(event))
            return
        [x(event, s) for x in handlers]
