# -*- coding: utf-8 -*-
import json


class ContractManager:
    def __init__(self, abi_path: str):
        with open(abi_path) as json_file:
            self.data = json.load(json_file)

    def get_contract_abi(self, contract_name: str) -> dict:
        """ Returns the ABI for a given contract. """
        return self.data[contract_name]['abi']

    def get_event_abi(self, contract_name: str, event_name: str):
        """ Returns the ABI for a given event. """
        contract_abi = self.get_contract_abi(contract_name)
        result = [
            x for x in contract_abi
            if x['type'] == 'event' and x['name'] == event_name
        ]

        if len(result) == 0:
            raise KeyError(f"Event '{event_name}' not found.")

        return result
