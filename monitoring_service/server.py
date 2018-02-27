from monitoring_service.transport import Transport
import logging
import gevent
import random
import time
import sys
import traceback

from monitoring_service.blockchain import BlockchainMonitor
from monitoring_service.state_db import StateDB
from monitoring_service.messages import Message, BalanceProof
from monitoring_service.constants import (
    EVENT_CHANNEL_CLOSE,
    EVENT_CHANNEL_CREATE,
    MAX_BALANCE_PROOF_AGE
)
from monitoring_service.gevent_error_handler import register_error_handler

from eth_utils import (
    is_checksum_address
)

log = logging.getLogger(__name__)

from monitoring_service.utils import privkey_to_addr


def order_participants(p1: str, p2: str):
    return (p1, p2) if p1 < p2 else (p2, p1)


def error_handler(context, exc_info):
    log.fatal("Unhandled exception terminating the program")
    traceback.print_exception(
        etype=exc_info[0],
        value=exc_info[1],
        tb=exc_info[2]
    )
    sys.exit()


class MonitoringService(gevent.Greenlet):
    def __init__(
        self,
        private_key: str,
        state_db: StateDB = None,
        transport: Transport = None,
        blockchain: BlockchainMonitor = None
    ) -> None:
        super().__init__()
        assert isinstance(private_key, str)
        assert isinstance(transport, Transport)
        assert isinstance(blockchain, BlockchainMonitor)
        assert isinstance(state_db, StateDB)
        self.private_key = private_key
        self.transport = transport
        self.blockchain = blockchain
        self.state_db = state_db
        self.is_running = gevent.event.Event()
        self.channels = {}          # channel_address: channel
        assert is_checksum_address(privkey_to_addr(self.private_key))
        self.transport.add_message_callback(lambda message: self.on_message_event(message))
        self.transport.privkey = lambda: self.private_key

    def _run(self):
        register_error_handler(error_handler)
        self.transport.start()
        self.blockchain.start()
        self.blockchain.register_handler(
            EVENT_CHANNEL_CLOSE,
            lambda channel: self.on_channel_close(channel)
        )
        self.blockchain.register_handler(
            EVENT_CHANNEL_CREATE,
            lambda channel: self.on_channel_create(channel)
        )

        self.is_running.wait()

    def stop(self):
        self.is_running.set()

    def on_channel_close(self, event):
        log.info('on channel close: %s' % str(event))
        event = event['data']
        # check if we have balance proof for the closing
        if event['channel_address'] not in self.state_db.balance_proofs:
            return
        balance_proof = self.state_db.balance_proofs[event['channel_address']]
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
            balance_proof.participant1,
            balance_proof.participant2
        )
        participant1_event, participant2_event = order_participants(
            event['participant1'],
            event['participant2']
        )
        return ((participant1_bp == participant1_event) and
                (participant2_bp == participant2_event) and
                (balance_proof.channel_address == event['channel_address']))

    def on_channel_create(self, event):
        log.info('on channel create: %s' % str(event))
        event = event['data']
        self.channels[event['channel_address']] = event

    def check_event(self, event):
        return random.random() < 0.3

    def challenge_proof(self, balance_proof_msg: BalanceProof):
        balance_proof = self.state_db.balance_proofs.get(
            balance_proof_msg['channel_address'], None
        )
        log.info('challenging proof event=%s BP=%s' % (balance_proof_msg, balance_proof))

    def on_message_event(self, message):
        """This handles messages received over the Transport"""
        assert isinstance(message, Message)
        if isinstance(message, BalanceProof):
            self.on_balance_proof(message)

    def on_balance_proof(self, balance_proof):
        assert isinstance(balance_proof, BalanceProof)
        existing_bp = self.state_db.balance_proofs.get(balance_proof.channel_address, None)
        if existing_bp is not None:
            if existing_bp.timestamp > balance_proof.timestamp:
                log.warning('attempt to update with an older BP: stored=%s, received=%s' %
                            (existing_bp, balance_proof))
                return
        bp_age = time.time() - balance_proof.timestamp
        if bp_age > MAX_BALANCE_PROOF_AGE:
            log.info('Not accepting BP: too old. diff=%d bp=%s' % (bp_age, balance_proof))
            return

        if bp_age < 0:
            log.info('Not accepting BP: time mismatch. bp=%s' % balance_proof)
            return

        log.info('received balance proof: %s' % str(balance_proof))
        self.state_db.store_balance_proof(balance_proof.serialize_data())

    @property
    def balance_proofs(self):
        return self.state_db.balance_proofs
