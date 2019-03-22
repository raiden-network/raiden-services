import pytest

from pathfinding_service.model.token_network import TokenNetwork
from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path


@pytest.fixture(scope='session')
def contracts_manager():
    return ContractManager(contracts_precompiled_path())


@pytest.fixture
def token_network_model(token_network) -> TokenNetwork:
    return TokenNetwork(token_network.address, token_network.address)
