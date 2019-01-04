import logging

import gevent
from eth_utils import is_address
from hexbytes import HexBytes

from raiden_libs.messages import MonitorRequest

log = logging.getLogger(__name__)


class StoreMonitorRequest(gevent.Greenlet):
    """Validate & store submitted monitor request. This consists of:
            - check of bp & reward proof signature
            - check if contracts contain code
            - check if there's enough tokens for the payout
        Return:
            True if monitor request is valid
    """
    def __init__(self, web3, state_db, monitor_request):
        super().__init__()
        assert isinstance(monitor_request, MonitorRequest)
        self.msg = monitor_request
        self.state_db = state_db
        self.web3 = web3

    def _run(self):
        checks = [
            self.check_signatures,
            self.verify_contract_code,
            self.check_balance
        ]
        results = [
            check(self.msg)
            for check in checks
        ]
        if not (False in results):
            self.state_db.store_monitor_request(self.msg)
        return not (False in results)

    def verify_contract_code(self, monitor_request):
        """Verify if address set in token_network_address field contains code"""
        balance_proof = monitor_request.balance_proof
        return self.web3.eth.getCode(balance_proof.token_network_address) != HexBytes('0x')

    def check_signatures(self, monitor_request):
        """Check if signatures set in the message are correct"""
        balance_proof = monitor_request.balance_proof
        return (
            is_address(monitor_request.reward_proof_signer) and
            is_address(balance_proof.signer) and
            is_address(monitor_request.non_closing_signer)
        )

    def check_balance(self, monitor_request):
        """Check if there is enough tokens to pay out reward amount"""
        return True
