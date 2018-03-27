import logging
import pytest
import gevent

import rlp
from eth_utils import decode_hex, denoms
from ethereum.transactions import Transaction
from eth_tester import EthereumTester, PyEVMBackend


from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider
from web3.providers.rpc import HTTPProvider

from raiden_libs.utils import (
    address_from_signature,
    keccak256,
)

DEFAULT_TIMEOUT = 5
DEFAULT_RETRY_INTERVAL = 3
FAUCET_ALLOWANCE = 100 * denoms.ether
INITIAL_TOKEN_SUPPLY = 200000000000
WEB3_PROVIDER_DEFAULT = 'http://localhost:8545'

log = logging.getLogger(__name__)


@pytest.fixture(scope='session')
def use_tester(request):
    return request.config.getoption('use_tester')


@pytest.fixture(scope='session')
def ethereum_tester():
    """Returns an instance of an Ethereum tester"""
    return EthereumTester(PyEVMBackend())


@pytest.fixture
def deploy_contract(revert_chain):
    """Returns a function that deploys a compiled contract"""
    def fn(
            web3,
            deployer_address,
            abi,
            bytecode,
            args
    ):
        contract = web3.eth.contract(abi=abi, bytecode=bytecode)
        txhash = contract.constructor(*args).transact({'from': deployer_address})
        contract_address = web3.eth.getTransactionReceipt(txhash).contractAddress
        web3.testing.mine(1)

        return contract(contract_address)
    return fn


@pytest.fixture(scope='session')
def web3(
        use_tester: bool,
        faucet_private_key: str,
        faucet_address: str,
        ethereum_tester
):
    """Returns an initialized Web3 instance"""
    if use_tester:
        provider = EthereumTesterProvider(ethereum_tester)
        web3 = Web3(provider)

        # Tester chain uses Transaction to send and validate transactions but does not support
        # EIP-155 yet. This patches the sender address recovery to handle EIP-155.
        sender_property_original = Transaction.sender.fget

        def sender_property_patched(self: Transaction):
            if self._sender:
                return self._sender

            if self.v and self.v >= 35:
                v = bytes([self.v])
                r = self.r.to_bytes(32, byteorder='big')
                s = self.s.to_bytes(32, byteorder='big')
                raw_tx = Transaction(
                    self.nonce, self.gasprice, self.startgas, self.to, self.value, self.data,
                    (self.v - 35) // 2, 0, 0
                )
                msg = keccak256(rlp.encode(raw_tx))
                self._sender = decode_hex(address_from_signature(r + s + v, msg))
                return self._sender
            else:
                return sender_property_original(self)

        Transaction.sender = property(
            sender_property_patched,
            Transaction.sender.fset,
            Transaction.sender.fdel
        )

        # add faucet account to tester
        ethereum_tester.add_account(faucet_private_key)

        # make faucet rich
        ethereum_tester.send_transaction({
            'from': ethereum_tester.get_accounts()[0],
            'to': faucet_address,
            'gas': 21000,
            'value': FAUCET_ALLOWANCE
        })

    else:
        rpc = HTTPProvider(WEB3_PROVIDER_DEFAULT)
        web3 = Web3(rpc)

    yield web3


@pytest.fixture(scope='session')
def wait_for_blocks(web3, kovan_block_time, use_tester):
    """Returns a function that blocks until n blocks are mined"""
    def wait_for_blocks(n):
        if use_tester:
            web3.testing.mine(n)
            gevent.sleep(0)
        else:
            target_block = web3.eth.blockNumber + n
            while web3.eth.blockNumber < target_block:
                gevent.sleep(kovan_block_time / 2)
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
def revert_chain(web3: Web3, use_tester):
    """Reverts chain to its initial state.
    If this fixture is used, the chain will revert on each test teardown.

    This is useful especially when using ethereum tester - its log filtering
    is very slow once enough events are present on-chain.

    Note that `deploy_contract` fixture uses `revert_chain` by default.
    """
    if use_tester:
        snapshot_id = web3.testing.snapshot()
        yield
        web3.testing.revert(snapshot_id)
    else:
        yield
