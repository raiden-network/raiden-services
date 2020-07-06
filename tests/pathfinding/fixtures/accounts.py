# pylint: disable=redefined-outer-name
from typing import List

import pytest
from eth_utils import keccak

from raiden.utils.typing import Address
from raiden_contracts.utils.type_aliases import PrivateKey
from raiden_libs.utils import private_key_to_address
from tests.pathfinding.config import NUMBER_OF_NODES


@pytest.fixture(scope="session")
def private_keys() -> List[PrivateKey]:
    offset = 14789632
    return [PrivateKey(keccak(offset + i)) for i in range(NUMBER_OF_NODES)]


@pytest.fixture(scope="session")
def addresses(private_keys: List[PrivateKey]) -> List[Address]:
    return [private_key_to_address(private_key) for private_key in private_keys]
