import logging
from typing import Callable

from raiden_libs.blockchain import BlockchainListener
from raiden_libs.utils import decode_contract_call

log = logging.getLogger(__name__)


class BlockchainMonitor(BlockchainListener):
    def __init__(self, web3, contract_manager, **kwargs) -> None:
        super().__init__(
            web3,
            contract_manager,
            'TokenNetwork',
            poll_interval=1,
            **kwargs
        )
        self.contract_manager = contract_manager

    def add_confirmed_listener(self, event_name: str, callback: Callable):
        """ Add a callback to listen for confirmed events. """
        return super().add_confirmed_listener(
            event_name,
            lambda event: self.handle_event(event, callback)
        )

    def handle_event(self, event, callback: Callable):
        tx = self.web3.eth.getTransaction(event['transactionHash'])
        log.info(str(event) + str(tx))
        abi = self.contract_manager.get_contract_abi('TokenNetwork')
        assert abi is not None
        method_params = decode_contract_call(abi, tx['data'])
        if method_params is not None:
            return callback(event, method_params)
        else:
            return None
