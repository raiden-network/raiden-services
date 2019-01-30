from copy import deepcopy

from eth_abi import decode_abi
from web3.contract import Contract
from web3.utils.abi import get_abi_output_types

from raiden_libs.contract import GAS_LIMIT_CONTRACT, GAS_PRICE, sign_transaction_data
from raiden_libs.utils import private_key_to_address


class Callable():
    """Replaces web3.contract.ContractFunction in the contract.functions map"""
    def __init__(self, call):
        self._call = call

    def transact(self, *args, **kwargs) -> bytes:
        """Creates a transaction, signs it with a provided private key and sends it. """
        args = deepcopy(args)
        private_key = kwargs.pop('private_key', None)
        if len(args) == 0:
            args = ({},)
        # buildTransaction requires 'from' field to be set properly
        args[0]['from'] = private_key_to_address(private_key)
        gas_limit = args[0].pop('gas_limit', GAS_LIMIT_CONTRACT)
        gas_price = args[0].pop('gasPrice', GAS_PRICE)
        tx_data = self._call.buildTransaction(*args, **kwargs)
        data = sign_transaction_data(
            private_key,
            self._call.web3,
            tx_data,
            gas_limit=gas_limit,
            gas_price=gas_price,
        )
        return self._call.web3.eth.sendRawTransaction(data.rawTransaction)

    def call(self, *args, **kwargs):
        kwargs.pop('private_key', None)
        from_address = None
        if len(args) == 1:
            from_address = args[0].pop('from', None)
        tx = self._call.buildTransaction(*args, **kwargs)
        if from_address is not None:
            tx['from'] = from_address
        output_types = get_abi_output_types(self._call.abi)
        return_data = self._call.web3.eth.call(tx)
        decoded = decode_abi(output_types, return_data)
        return decoded[0] if len(decoded) == 1 else decoded


class FunctionsMap:
    """This replaces `function` attribute of the wrapped contract"""
    def __init__(self, abi, contract):
        self.contract = contract

    def __getattr__(self, attr):
        return lambda *args, **kwargs: self.get_call(attr, *args, **kwargs)

    def get_call(self, attr, *args, **kwargs):
        call = getattr(self.contract.functions, attr)(*args, **kwargs)
        return Callable(call)


class PrivateContract:
    """This class allows using of web3.contract with a non-eth node account.
    Usage:
        contract = web3.eth.contract(abi=..., address=...)
        wrapped_contract = PrivateContract(contract)
        contract.functions.my_awesome_function().transact(private_key=my_key)
    """
    def __init__(self, contract):
        self.contract = contract
        self.functions = FunctionsMap(self.contract.abi, contract)

    def constructor(self, *args, **kwargs) -> Callable:
        call = self.contract.constructor(*args, **kwargs)
        return Callable(call)

    def __getattr__(self, attr):
        if attr == 'functions':
            return self.functions
        else:
            return Contract.__getattribute__(self.contract, attr)
