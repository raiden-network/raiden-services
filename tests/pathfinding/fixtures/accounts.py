from typing import List

import pytest
from eth_utils import encode_hex, keccak
from tests.pathfinding.config import NUMBER_OF_NODES

from raiden_libs.types import Address
from raiden_libs.utils import private_key_to_address


@pytest.fixture(scope='session')
def private_keys() -> List[str]:
    offset = 14789632
    return [encode_hex(keccak(offset + i)) for i in range(NUMBER_OF_NODES)]


@pytest.fixture(scope='session')
def addresses(private_keys: List[str]) -> List[Address]:
    return [
        Address(private_key_to_address(private_key))
        for private_key in private_keys
    ]


@pytest.fixture(scope='session')
def initiator_private_key(private_keys: List[str]) -> str:
    return private_keys[0]


@pytest.fixture(scope='session')
def target_private_key(private_keys: List[str]) -> str:
    return private_keys[1]


@pytest.fixture(scope='session')
def initiator_address(initiator_private_key: str) -> Address:
    return Address(private_key_to_address(initiator_private_key))


@pytest.fixture(scope='session')
def target_address(target_private_key: str) -> Address:
    return Address(private_key_to_address(target_private_key))
