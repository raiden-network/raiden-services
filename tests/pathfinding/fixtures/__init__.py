import pytest

from pathfinding_service.model.token_network import TokenNetwork
from raiden.utils.typing import TokenNetworkAddress
from tests.constants import DEFAULT_TOKEN_NETWORK_SETTLE_TIMEOUT

from ..utils import SimpleReachabilityContainer
from .accounts import *  # noqa
from .api import *  # noqa
from .iou import *  # noqa
from .network_service import *  # noqa


@pytest.fixture
def token_network_model() -> TokenNetwork:
    return TokenNetwork(TokenNetworkAddress(bytes([1] * 20)), DEFAULT_TOKEN_NETWORK_SETTLE_TIMEOUT)


@pytest.fixture
def reachability_state() -> SimpleReachabilityContainer:
    return SimpleReachabilityContainer({})
