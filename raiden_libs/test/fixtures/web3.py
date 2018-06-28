import logging
import pytest
import gevent

from eth_utils import denoms
from eth_tester import EthereumTester, PyEVMBackend
from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider

from raiden_libs.types import Address

DEFAULT_TIMEOUT = 5
DEFAULT_RETRY_INTERVAL = 3
FAUCET_ALLOWANCE = 100 * denoms.ether
INITIAL_TOKEN_SUPPLY = 200000000000

log = logging.getLogger(__name__)


@pytest.fixture(scope='session')
def ethereum_tester():
    """Returns an instance of an Ethereum tester"""
    tester = EthereumTester(PyEVMBackend())
    tester.set_fork_block('FORK_BYZANTIUM', 0)
    return tester


@pytest.fixture
def deploy_contract_txhash(revert_chain):
    """Returns a function that deploys a compiled contract, returning a txhash"""
    def fn(
            web3,
            deployer_address,
            abi,
            bytecode,
            args,
    ):
        if args is None:
            args = []
        contract = web3.eth.contract(abi=abi, bytecode=bytecode)
        return contract.constructor(*args).transact({'from': deployer_address})
    return fn


@pytest.fixture
def deploy_contract(revert_chain, deploy_contract_txhash):
    """Returns a function that deploys a compiled contract"""
    def fn(
            web3,
            deployer_address,
            abi,
            bytecode,
            args,
    ):
        contract = web3.eth.contract(abi=abi, bytecode=bytecode)
        txhash = deploy_contract_txhash(web3, deployer_address, abi, bytecode, args)
        contract_address = web3.eth.getTransactionReceipt(txhash).contractAddress
        web3.testing.mine(1)

        return contract(contract_address)
    return fn


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
        faucet_private_key: str,
        faucet_address: Address,
        ethereum_tester,
):
    """Returns an initialized Web3 instance"""
    provider = EthereumTesterProvider(ethereum_tester)
    web3 = Web3(provider)

    # add faucet account to tester
    ethereum_tester.add_account(faucet_private_key)

    # make faucet rich
    ethereum_tester.send_transaction({
        'from': ethereum_tester.get_accounts()[0],
        'to': faucet_address,
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


@pytest.fixture
def revert_chain(web3: Web3):
    """Reverts chain to its initial state.
    If this fixture is used, the chain will revert on each test teardown.

    This is useful especially when using ethereum tester - its log filtering
    is very slow once enough events are present on-chain.

    Note that `deploy_contract` fixture uses `revert_chain` by default.
    """
    snapshot_id = web3.testing.snapshot()
    yield
    web3.testing.revert(snapshot_id)
