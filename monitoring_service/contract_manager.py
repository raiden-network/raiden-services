import os
import logging
from ethereum.tools import _solidity
from monitoring_service.config import CONTRACTS_DIR

log = logging.getLogger(__name__)


class ContractManager:
    def __init__(self, path: str) -> None:
        self.abi = ContractManager.load_contracts(path)

    @staticmethod
    def load_contracts(path) -> dict:
        ret = {}
        for contract in os.listdir(path):
            contract_path = os.path.join(path, contract)
            contract_name = os.path.basename(contract).split('.')[0]
            ret[contract_name] = _solidity.compile_contract(
                contract_path, contract_name,
                combined='abi'
            )
        return ret

    def get_contract_abi(self, contract_name: str) -> dict:
        return self.abi[contract_name]

    def get_event_abi(self, contract_name: str, event_name: str):
        contract_abi = self.get_contract_abi(contract_name)
        return [
            x for x in contract_abi['abi']
            if x['type'] == 'event' and x['name'] == event_name
        ]


CONTRACT_MANAGER = ContractManager(CONTRACTS_DIR)
