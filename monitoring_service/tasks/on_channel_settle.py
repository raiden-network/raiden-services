import logging

import gevent

log = logging.getLogger(__name__)


class OnChannelSettle(gevent.Greenlet):
    """Executed whenever a channel is settled"""
    def __init__(self, monitor_request, monitor_contract, privkey):
        super().__init__()
        self.monitor_contract = monitor_contract
        self.monitor_request = monitor_request
        self.private_key = privkey

    def _run(self):
        return self.claim_reward(
            self.monitor_contract,
            self.monitor_request,
            self.private_key
        )

    @staticmethod
    def claim_reward(contract, monitor_request, private_key):
        web3 = contract.web3

        tx_hash = contract.functions.claimReward(
            monitor_request.balance_proof.channel_identifier,
            monitor_request.balance_proof.token_network_address,
            monitor_request.balance_proof.signer,
            monitor_request.non_closing_signer
        ).transact({'gas': 210000}, private_key=private_key)
        receipt = web3.eth.getTransactionReceipt(tx_hash)
        tx = web3.eth.getTransactionReceipt(tx_hash)
        log.info(receipt)
        log.info(tx)
        return True
