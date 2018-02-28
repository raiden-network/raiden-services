import logging
import pytest
import gevent
import types

import rlp
from _pytest.monkeypatch import MonkeyPatch
from eth_utils import decode_hex, denoms
from ethereum.transactions import Transaction
from eth_tester import EthereumTester, PyEVMBackend
#from populus.wait import Wait

from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider
from web3.contract import Contract
from web3.providers.rpc import HTTPProvider

from monitoring_service.utils import (
    addr_from_sig,
    keccak256,
)
# import microraiden.utils.contract

DEFAULT_TIMEOUT = 5
DEFAULT_RETRY_INTERVAL = 3
FAUCET_ALLOWANCE = 100 * denoms.ether
INITIAL_TOKEN_SUPPLY = 200000000000
WEB3_PROVIDER_DEFAULT = 'http://localhost:8545'


@pytest.fixture(scope='session')
def ethereum_tester():
    return EthereumTester(PyEVMBackend())


@pytest.fixture(scope='session')
def mine_sync_event():
    return gevent.event.Event()


@pytest.fixture(scope='session', autouse=True)
def disable_requests_loggin():
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)


@pytest.fixture
def deploy_contract():
    def fn(
            web3,
            deployer_address,
            abi,
            bytecode,
            args
    ):
        contract = web3.eth.contract(abi=abi, bytecode=bytecode)
        txhash = contract.deploy({'from': deployer_address}, args=args)
        contract_address = web3.eth.getTransactionReceipt(txhash).contractAddress
        web3.testing.mine(1)

        return contract(contract_address)
    return fn


@pytest.fixture(scope='session')
def web3(use_tester: bool,
         faucet_private_key: str,
         faucet_address: str,
         mine_sync_event,
         ethereum_tester
         ):
    if use_tester:
        provider = EthereumTesterProvider(ethereum_tester)
        web3 = Web3(provider)
        x = web3.testing.mine

        def mine_patched(self, count):
            x(count)
            mine_sync_event.set()
            gevent.sleep(0)  # switch context
            mine_sync_event.clear()

        web3.testing.mine = types.MethodType(
            mine_patched, web3.testing.mine
        )

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
                self._sender = decode_hex(addr_from_sig(r + s + v, msg))
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


@pytest.fixture
def patched_contract(use_tester: bool, monkeypatch: MonkeyPatch, web3: Web3):
    if use_tester:
        def patched_get_logs_raw(contract: Contract, filter_params):
            filter_ = contract.web3.eth.filter(filter_params)
            response = contract.web3.eth.getFilterLogs(filter_.filter_id)
            contract.web3.eth.uninstallFilter(filter_.filter_id)
            return response

        def patched_wait_for_event(wait: float):
            web3.testing.mine(1)

        def patched_wait_for_transaction(
            web3: Web3,
            tx_hash: str,
            timeout: int = DEFAULT_TIMEOUT,
            polling_interval: int = DEFAULT_RETRY_INTERVAL
        ):
            web3.testing.mine(1)
            tx_receipt = web3.eth.getTransactionReceipt(tx_hash)
            if tx_receipt is None:
                raise TimeoutError('Transaction {} was not mined.'.format(tx_hash))
            return tx_receipt

#        monkeypatch.setattr(microraiden.utils.contract, '_get_logs_raw', patched_get_logs_raw)
#        monkeypatch.setattr(microraiden.utils.contract, '_wait', patched_wait_for_event)
#        monkeypatch.setattr(
#            microraiden.utils.contract,
#            'wait_for_transaction',
#            patched_wait_for_transaction
#        )


@pytest.fixture(scope='session')
def wait(web3, kovan_block_time):
    poll_interval = kovan_block_time / 2
#    return Wait(web3, poll_interval=poll_interval)


@pytest.fixture(scope='session')
def wait_for_blocks(web3, kovan_block_time, use_tester):
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
def wait_for_transaction(wait):
    def wait_for_transaction(tx_hash):
        wait.for_receipt(tx_hash)
        gevent.sleep(0)
    return wait_for_transaction


@pytest.fixture
def revert_chain(web3: Web3, use_tester: bool, sender_privkey: str, receiver_privkey: str):
    if use_tester:
        snapshot_id = web3.testing.snapshot()
        yield
        web3.testing.revert(snapshot_id)
    else:
        yield


@pytest.fixture(scope='session')
def token_contract(web3: Web3, token_address: str, token_abi):
    return web3.eth.contract(abi=token_abi, address=token_address)


@pytest.fixture(scope='session')
def channel_manager_contract(web3: Web3, channel_manager_address: str, channel_manager_abi):
    return web3.eth.contract(abi=channel_manager_abi, address=channel_manager_address)
