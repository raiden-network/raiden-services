from typing import List, Any

import rlp
from eth_utils import decode_hex, encode_hex, denoms
from ethereum.transactions import Transaction
from web3 import Web3
from web3.contract import Contract

from raiden_libs.utils import private_key_to_address, sign_transaction

DEFAULT_TIMEOUT = 60
DEFAULT_RETRY_INTERVAL = 3
GAS_PRICE = 20 * denoms.gwei
GAS_LIMIT_POT = 21000
GAS_LIMIT_CONTRACT = 130000


def create_signed_transaction(
        private_key: str,
        web3: Web3,
        to: str,
        value: int=0,
        data=b'',
        nonce_offset: int = 0,
        gas_price: int = GAS_PRICE,
        gas_limit: int = GAS_LIMIT_POT
) -> str:
    """Creates a signed on-chain transaction compliant with EIP155."""
    tx = create_transaction(
        web3=web3,
        from_=private_key_to_address(private_key),
        to=to,
        value=value,
        data=data,
        nonce_offset=nonce_offset,
        gas_price=gas_price,
        gas_limit=gas_limit
    )
    sign_transaction(tx, private_key, int(web3.version.network))
    return encode_hex(rlp.encode(tx))


def create_transaction(
        web3: Web3,
        from_: str,
        to: str,
        data: bytes = b'',
        nonce_offset: int = 0,
        value: int = 0,
        gas_price: int = GAS_PRICE,
        gas_limit: int = GAS_LIMIT_POT
) -> Transaction:
    """Create a transaction"""
    nonce = web3.eth.getTransactionCount(from_, 'pending') + nonce_offset
    tx = Transaction(nonce, gas_price, gas_limit, to, value, data)
    tx.sender = decode_hex(from_)
    return tx


def create_signed_contract_transaction(
        private_key: str,
        contract: Contract,
        func_name: str,
        args: List[Any],
        value: int=0,
        nonce_offset: int = 0,
        gas_price: int = GAS_PRICE,
        gas_limit: int = GAS_LIMIT_POT
) -> str:
    """Creates a signed on-chain contract transaction compliant with EIP155."""
    tx = create_contract_transaction(
        contract=contract,
        from_=private_key_to_address(private_key),
        func_name=func_name,
        args=args,
        value=value,
        nonce_offset=nonce_offset,
        gas_price=gas_price,
        gas_limit=gas_limit
    )
    sign_transaction(tx, private_key, int(contract.web3.version.network))
    return encode_hex(rlp.encode(tx))


def create_contract_transaction(
        contract: Contract,
        from_: str,
        func_name: str,
        args: List[Any],
        value: int = 0,
        nonce_offset: int = 0,
        gas_price: int = GAS_PRICE,
        gas_limit: int = GAS_LIMIT_POT
) -> Transaction:
    data = create_transaction_data(contract, func_name, args)
    return create_transaction(
        web3=contract.web3,
        from_=from_,
        to=contract.address,
        value=value,
        data=data,
        nonce_offset=nonce_offset,
        gas_price=gas_price,
        gas_limit=gas_limit
    )


def create_transaction_data(contract: Contract, func_name: str, args: List[Any]) -> bytes:
    data = contract._prepare_transaction(func_name, args)['data']
    return decode_hex(data)
