import json
import logging

import gevent
import pytest
from eth_account import Account
from tests.constants import KEYSTORE_FILE_NAME, KEYSTORE_PASSWORD
from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider

from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path
from raiden_contracts.tests.utils.constants import (
    FAUCET_ADDRESS,
    FAUCET_ALLOWANCE,
    FAUCET_PRIVATE_KEY,
)

log = logging.getLogger(__name__)


@pytest.fixture(scope='session')
def web3(patch_genesis_gas_limit, ethereum_tester):
    """Returns an initialized Web3 instance"""
    provider = EthereumTesterProvider(ethereum_tester)
    web3 = Web3(provider)
    web3.eth.estimateGas = lambda txn: 5_500_000

    # add faucet account to tester
    ethereum_tester.add_account(FAUCET_PRIVATE_KEY)

    # make faucet rich
    ethereum_tester.send_transaction(
        {
            'from': ethereum_tester.get_accounts()[0],
            'to': FAUCET_ADDRESS,
            'gas': 21000,
            'value': FAUCET_ALLOWANCE,
        }
    )

    yield web3


@pytest.fixture(scope='session')
def wait_for_blocks(web3):
    """Returns a function that blocks until n blocks are mined"""

    def wait_for_blocks(n):
        web3.testing.mine(n)
        gevent.sleep()

    return wait_for_blocks


@pytest.fixture(scope='session')
def contracts_manager():
    """Overwrites the contracts_manager from raiden_contracts to use compiled contracts """
    return ContractManager(contracts_precompiled_path())


@pytest.fixture
def keystore_file(tmp_path) -> str:
    keystore_file = tmp_path / KEYSTORE_FILE_NAME

    account = Account.create()
    keystore_json = Account.encrypt(private_key=account.privateKey, password=KEYSTORE_PASSWORD)
    with open(keystore_file, 'w') as fp:
        json.dump(keystore_json, fp)

    return keystore_file
