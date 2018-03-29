import logging
from raiden_contracts.contract_manager import CONTRACT_MANAGER
from raiden_libs.utils import decode_contract_call
from raiden_libs.blockchain import BlockchainListener

log = logging.getLogger(__name__)


class BlockchainMonitor(BlockchainListener):
    def __init__(self, web3, **kwargs):
        super().__init__(
            web3,
            CONTRACT_MANAGER,
            'TokenNetwork',
            poll_interval=1,
            **kwargs
        )

    def add_confirmed_listener(self, event_name: str, callback: callable):
        """ Add a callback to listen for confirmed events. """
        return super().add_confirmed_listener(
            event_name,
            lambda event: self.handle_event(event, callback)
        )

    def handle_event(self, event, callback):
        tx = self.web3.eth.getTransaction(event['transactionHash'])
        abi = CONTRACT_MANAGER.get_contract_abi('TokenNetwork')
        method_params = decode_contract_call(abi, tx['data'])
        assert method_params is not None
        return callback(event, method_params)
