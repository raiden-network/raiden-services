import json

import pytest
from eth_account import Account

from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path

KEYSTORE_FILE_NAME = 'keystore.txt'
KEYSTORE_PASSWORD = 'password'


@pytest.fixture(scope='session')
def contracts_manager():
    """Overwrites the contracts_manager from raiden_contracts to use compiled contracts """
    return ContractManager(contracts_precompiled_path())


@pytest.fixture
def keystore_file(tmp_path) -> str:
    keystore_file = tmp_path / KEYSTORE_FILE_NAME

    account = Account.create()
    keystore_json = Account.encrypt(
        private_key=account.privateKey,
        password=KEYSTORE_PASSWORD,
    )
    with open(keystore_file, 'w') as fp:
        json.dump(keystore_json, fp)

    return keystore_file
