import random
from typing import Callable

import pytest
from eth_utils import encode_hex

from monitoring_service.states import MonitorRequest
from raiden_libs.types import ChannelIdentifier
from raiden_libs.utils import UINT64_MAX, UINT256_MAX, private_key_to_address, sha3
from raiden_libs.utils.signing import eth_sign


@pytest.fixture
def get_random_private_key() -> Callable:
    """Returns a function returning a random private key"""
    return lambda: "0x%064x" % random.randint(
        1,
        UINT256_MAX,
    )


@pytest.fixture
def get_random_address(get_random_private_key) -> Callable:
    """Returns a function returning a random valid ethereum address"""
    def f():
        return private_key_to_address(get_random_private_key())
    return f


@pytest.fixture
def get_random_identifier() -> Callable:
    """Returns a function returning a random valid ethereum address"""
    def f():
        return ChannelIdentifier(random.randint(0, UINT256_MAX))
    return f


@pytest.fixture
def get_random_monitor_request(get_random_address, get_random_private_key, get_random_identifier):
    def f():
        contract_address = get_random_address()
        channel_identifier = get_random_identifier()

        balance_hash_data = '%d' % random.randint(0, UINT64_MAX)
        additional_hash_data = '%d' % random.randint(0, UINT64_MAX)

        balance_hash = encode_hex(sha3(balance_hash_data.encode()))
        nonce = random.randint(0, UINT64_MAX)
        additional_hash = encode_hex(sha3(additional_hash_data.encode()))
        chain_id = 1

        privkey = get_random_private_key()
        privkey_non_closing = get_random_private_key()

        monitor_request = MonitorRequest(
            channel_identifier=channel_identifier,
            token_network_address=contract_address,
            chain_id=chain_id,
            balance_hash=balance_hash,
            nonce=nonce,
            additional_hash=additional_hash,
            closing_signature='',
            non_closing_signature='',
            reward_amount=0,
            reward_proof_signature='',
        )
        monitor_request.closing_signature = encode_hex(
            eth_sign(privkey, monitor_request.packed_balance_proof_data()),
        )
        monitor_request.non_closing_signature = encode_hex(
            eth_sign(privkey_non_closing, monitor_request.packed_non_closing_data()),
        )
        monitor_request.reward_proof_signature = encode_hex(
            eth_sign(privkey, monitor_request.packed_reward_proof_data()),
        )
        return monitor_request, privkey, privkey_non_closing
    return f


def test_monitor_request_properties(get_random_monitor_request):
    request, p1, p2 = get_random_monitor_request()

    assert request.signer == private_key_to_address(p1)
    assert request.non_closing_signer == private_key_to_address(p2)
    assert request.reward_proof_signer == private_key_to_address(p1)
