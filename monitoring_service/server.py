from monitoring_service.transport import MatrixTransport
import logging
import gevent
import json
import jsonschema
import random
import time

from monitoring_service.json_schema import BALANCE_PROOF_SCHEMA
from monitoring_service.blockchain import BlockchainMonitor
from monitoring_service.constants import (
    EVENT_CHANNEL_CLOSE,
    EVENT_CHANNEL_CREATE,
    MAX_BALANCE_PROOF_AGE
)

from eth_utils import (
    is_checksum_address
)

log = logging.getLogger(__name__)

from monitoring_service.utils import privkey_to_addr


def order_participants(p1: str, p2: str):
    return (p1, p2) if p1 < p2 else (p2, p1)


class MonitoringService():
    def __init__(
        self,
        private_key: str,
        transport: MatrixTransport,
        blockchain: BlockchainMonitor
    ) -> None:
        self.private_key = private_key
        self.transport = transport
        self.blockchain = blockchain
        self.is_running = gevent.event.Event()
        self.balance_proofs = {}    # address: balance_proof
        self.channels = {}          # channel_address: channel
        assert is_checksum_address(privkey_to_addr(self.private_key))

    def sync_history(self):
        self.transport.sync_history()

    def run(self):
        self.transport.connect()
        self.blockchain.start()
        self.transport.add_listener(lambda room, event: self.dispatch_matrix(room, event))
        self.blockchain.register_handler(
            EVENT_CHANNEL_CLOSE,
            lambda channel: self.on_channel_close(channel)
        )
        self.blockchain.register_handler(
            EVENT_CHANNEL_CREATE,
            lambda channel: self.on_channel_create(channel)
        )
        self.sync_history()

        self.is_running.wait()

    def stop(self):
        self.is_running.set()

    def on_channel_close(self, event):
        log.info('on channel close: %s' % str(event))
        event = event['data']
        # check if we have balance proof for the closing
        if event['channel_address'] not in self.balance_proofs:
            return
        balance_proof = self.balance_proofs[event['channel_address']]
        if self.check_event_data(balance_proof, event) is False:
            log.warning('Event data do not match balance proof data! event=%s, bp=%s'
                        % (event, balance_proof))
            return

        # check if we should challenge closeChannel
        if self.check_event(event) is False:
            log.warning('Invalid balance proof submitted! Challenging! event=%s' % event)
            self.challenge_proof(event)

    def check_event_data(self, balance_proof: dict, event: dict):
        participant1_bp, participant2_bp = order_participants(
            balance_proof['participant1'],
            balance_proof['participant2']
        )
        participant1_event, participant2_event = order_participants(
            event['participant1'],
            event['participant2']
        )
        return ((participant1_bp == participant1_event) and
                (participant2_bp == participant2_event) and
                (balance_proof['channel_address'] == event['channel_address']))

    def on_channel_create(self, event):
        log.info('on channel create: %s' % str(event))
        event = event['data']
        self.channels[event['channel_address']] = event

    def check_event(self, event):
        return random.random() < 0.3

    def challenge_proof(self, event):
        balance_proof = self.balance_proofs.get(event['channel_address'], None)
        log.info('challenging proof event=%s BP=%s' % (event, balance_proof))

    def on_message_event(self, event):
        try:
            msg = json.loads(event['content']['body'])
        except ValueError:
            return

        try:
            jsonschema.validate(msg, BALANCE_PROOF_SCHEMA)
        except jsonschema.exceptions.ValidationError:
            return

        existing_bp = self.balance_proofs.get(msg['channel_address'], None)
        if existing_bp is not None:
            if existing_bp['timestamp'] > msg['timestamp']:
                log.warning('attempt to update with an older BP: stored=%s, received=%s' %
                            (existing_bp, msg))
                return
        bp_age = time.time() - msg['timestamp']
        if bp_age > MAX_BALANCE_PROOF_AGE:
            log.info('Not accepting BP: too old. diff=%d bp=%s' % (bp_age, msg))
            return

        if bp_age < 0:
            log.info('Not accepting BP: time mismatch. bp=%s' % msg)
            return

        log.info('received balance proof: %s' % str(msg))
        self.balance_proofs[msg['channel_address']] = msg

    def dispatch_matrix(self, room, event):
        if event['type'] == "m.room.member":
            membership = event.get('membership', None)
            if membership == "join":
                log.debug("{0} joined".format(event['content']['displayname']))
        elif event['type'] == "m.room.message":
            if event['content']['msgtype'] == "m.text":
                self.on_message_event(event)
                log.debug("{0}: {1}".format(event['sender'], event['content']['body']))
        else:
            log.debug(event['type'])
