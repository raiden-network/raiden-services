from typing import Dict

from eth_utils import denoms
from web3 import Web3

from raiden_libs.utils import private_key_to_address

DEFAULT_TIMEOUT = 60
DEFAULT_RETRY_INTERVAL = 3
GAS_PRICE = 20 * denoms.gwei
GAS_LIMIT_POT = 21000
GAS_LIMIT_CONTRACT = 130000


def sign_transaction_data(
    private_key: str,
    web3: Web3,
    transaction: Dict,
    nonce_offset: int = 0,
    gas_price: int = GAS_PRICE,
    gas_limit: int = GAS_LIMIT_POT,
):
    from_ = private_key_to_address(private_key)
    transaction['gasPrice'] = gas_price
    transaction['gas'] = gas_limit
    transaction['nonce'] = web3.eth.getTransactionCount(from_, 'pending') + nonce_offset
    transaction['chainId'] = int(web3.version.network)
    return web3.eth.account.signTransaction(transaction, private_key)
