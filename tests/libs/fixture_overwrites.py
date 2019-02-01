import pytest
from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path


@pytest.fixture(scope='session')
def contracts_manager():
    return ContractManager(contracts_precompiled_path())


@pytest.fixture(scope='session')
def contract_deployer_address(faucet_address):
    return faucet_address
