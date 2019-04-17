import pytest

from pathfinding_service.model.token_network import TokenNetwork
from raiden_libs.types import TokenNetworkAddress

from .accounts import *  # noqa
from .api import *  # noqa
from .network_service import *  # noqa


@pytest.fixture
def token_network_model() -> TokenNetwork:
    return TokenNetwork(TokenNetworkAddress("0x" + "1" * 40))
