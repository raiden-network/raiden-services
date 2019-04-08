import pytest

from pathfinding_service.model.token_network import TokenNetwork


@pytest.fixture
def token_network_model(token_network) -> TokenNetwork:
    return TokenNetwork(token_network.address)
