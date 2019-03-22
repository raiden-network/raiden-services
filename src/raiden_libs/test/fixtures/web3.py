import logging

import gevent
import pytest
from eth_tester import EthereumTester, PyEVMBackend
from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider

from raiden_contracts.tests.utils.constants import (
    FAUCET_ADDRESS,
    FAUCET_ALLOWANCE,
    FAUCET_PRIVATE_KEY,
)

DEFAULT_TIMEOUT = 5
DEFAULT_RETRY_INTERVAL = 3
INITIAL_TOKEN_SUPPLY = 200000000000

log = logging.getLogger(__name__)


@pytest.fixture(scope='session')
def ethereum_tester():
    """Returns an instance of an Ethereum tester"""
    return EthereumTester(PyEVMBackend())


@pytest.fixture(scope='session')
def patch_genesis_gas_limit():
    import eth_tester.backends.pyevm.main as pyevm_main
    original_gas_limit = pyevm_main.GENESIS_GAS_LIMIT
    pyevm_main.GENESIS_GAS_LIMIT = 6 * 10 ** 6

    yield

    pyevm_main.GENESIS_GAS_LIMIT = original_gas_limit


@pytest.fixture(scope='session')
def web3(
        patch_genesis_gas_limit,
        ethereum_tester,
):
    """Returns an initialized Web3 instance"""
    provider = EthereumTesterProvider(ethereum_tester)
    web3 = Web3(provider)
    web3.eth.estimateGas = lambda txn: 5_500_000

    # add faucet account to tester
    ethereum_tester.add_account(FAUCET_PRIVATE_KEY)

    # make faucet rich
    ethereum_tester.send_transaction({
        'from': ethereum_tester.get_accounts()[0],
        'to': FAUCET_ADDRESS,
        'gas': 21000,
        'value': FAUCET_ALLOWANCE,
    })

    yield web3


@pytest.fixture(scope='session')
def wait_for_blocks(web3):
    """Returns a function that blocks until n blocks are mined"""
    def wait_for_blocks(n):
        web3.testing.mine(n)
        gevent.sleep()
    return wait_for_blocks


@pytest.fixture(scope='session')
def wait_for_transaction(web3):
    """Returns a function that waits until a transaction is mined"""
    def wait_for_transaction(tx_hash, max_blocks=5):
        block = web3.eth.blockNumber
        while True:
            tx = web3.eth.getTransactionReceipt(tx_hash)
            if tx is not None:
                return tx
            gevent.sleep(0.1)
            block_diff = web3.eth.blockNumber - block
            assert block_diff < max_blocks
    return wait_for_transaction
