import logging

import gevent

log = logging.getLogger(__name__)


class OnChannelClose(gevent.Greenlet):
    """Executed whenever a channel is closed and there's a monitor request
    record for this channel stored in the db.
    """
    def __init__(self, monitor_contract, monitor_request, privkey):
        super().__init__()
        self.monitor_contract = monitor_contract
        self.monitor_request = monitor_request
        self.private_key = privkey

    def _run(self):
        return self.submit_monitor_request(
            self.monitor_contract,
            self.monitor_request,
            self.private_key,
        )

    @staticmethod
    def submit_monitor_request(contract, monitor_request, private_key):
        balance_proof = monitor_request.balance_proof

        tx_hash = contract.functions.monitor(
            balance_proof.signer,
            monitor_request.non_closing_signer,
            balance_proof.balance_hash,
            balance_proof.nonce,
            balance_proof.additional_hash,
            balance_proof.signature,
            monitor_request.non_closing_signature,
            monitor_request.reward_amount,
            balance_proof.token_network_address,
            monitor_request.reward_proof_signature,
        ).transact({'gas_limit': 350000}, private_key=private_key)
        log.info(f'Submit MR to SC, got tx_hash {tx_hash}')
        assert tx_hash is not None
        return 0
