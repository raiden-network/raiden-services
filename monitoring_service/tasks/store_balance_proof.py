import time
import gevent
from monitoring_service.constants import (
    MAX_BALANCE_PROOF_AGE
)
import logging
from hexbytes import HexBytes

log = logging.getLogger(__name__)


class StoreBalanceProof(gevent.Greenlet):
    """Validate & store submitted balance proof. This consists of:
            - checking if on-chain data (i.e. channel address) are valid
            - verify the balance proof hash itself
            - verify balance proof age
        Parameters:
            web3: web3 instance
            balance_proof: a balance proof message.
        Return:
            True if balance proof is usable
    """
    def __init__(self, web3, state_db, balance_proof):
        super().__init__()
        self.balance_proof = balance_proof
        self.state_db = state_db
        self.web3 = web3

    def _run(self):
        checks = [
            self.verify_age,
            self.verify_contract_code,
            self.verify_existing_bp
        ]
        results = [
            check(self.balance_proof)
            for check in checks
        ]
        if not (False in results):
            serialized_bp = self.balance_proof.serialize_data()
            self.state_db.store_balance_proof(serialized_bp)
        return not (False in results)

    def verify_contract_code(self, balance_proof):
        return self.web3.eth.getCode(balance_proof.channel_address) != HexBytes('0x')

    @staticmethod
    def verify_age(balance_proof):
        bp_age = time.time() - balance_proof.timestamp
        if bp_age > MAX_BALANCE_PROOF_AGE:
            log.info('Not accepting BP: too old. diff=%d bp=%s' % (bp_age, balance_proof))
            return False

        if bp_age < 0:
            log.info('Not accepting BP: time mismatch. bp=%s' % balance_proof)
            return False
        return True

    def verify_existing_bp(self, balance_proof):
        # this may be part of state database...
        existing_bp = self.state_db.balance_proofs.get(balance_proof.channel_address, None)
        if existing_bp is None:
            return True
        if existing_bp['timestamp'] > balance_proof.timestamp:
            log.warning('attempt to update with an older BP: stored=%s, received=%s' %
                        (existing_bp, balance_proof))
            return False
        return True
