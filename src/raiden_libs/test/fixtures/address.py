import random
from typing import Callable

import pytest
from eth_utils import denoms, encode_hex, is_address

from raiden_libs.messages import BalanceProof, MonitorRequest
from raiden_libs.types import Address, ChannelIdentifier
from raiden_libs.utils import UINT64_MAX, UINT192_MAX, UINT256_MAX, private_key_to_address, sha3
from raiden_libs.utils.signing import eth_sign


@pytest.fixture
def get_random_privkey() -> Callable:
    """Returns a random private key"""
    return lambda: "0x%064x" % random.randint(
        1,
        UINT256_MAX,
    )


@pytest.fixture
def get_random_address(get_random_privkey) -> Callable:
    """Returns a random valid ethereum address"""
    def f():
        return private_key_to_address(get_random_privkey())
    return f


@pytest.fixture
def get_random_bp(get_random_address, get_random_privkey) -> Callable:
    """Returns a balance proof filled in with a random value"""
    def f(
        channel_identifier: ChannelIdentifier = None,
        contract_address: Address = None,
    ):
        contract_address = contract_address or get_random_address()
        channel_identifier = channel_identifier or ChannelIdentifier(
            random.randint(0, UINT256_MAX),
        )

        balance_hash_data = '%d' % random.randint(0, UINT64_MAX)
        additional_hash_data = '%d' % random.randint(0, UINT64_MAX)

        balance_proof = BalanceProof(
            channel_identifier,
            contract_address,
            balance_hash=encode_hex(sha3(balance_hash_data.encode())),
            nonce=random.randint(0, UINT64_MAX),
            additional_hash=encode_hex(sha3(additional_hash_data.encode())),
            chain_id=1,
        )
        return balance_proof

    return f


@pytest.fixture(scope='session')
def faucet_private_key():
    """Returns private key of a faucet used in tests"""
    return '0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'


@pytest.fixture(scope='session')
def faucet_address(faucet_private_key):
    """Returns address of a faucet used in tests"""
    return private_key_to_address(faucet_private_key)


@pytest.fixture
def send_funds(
    ethereum_tester,
    custom_token,
    faucet_address,
):
    """Send some tokens and eth to specified address."""
    def f(target: str):
        assert is_address(target)
        ethereum_tester.send_transaction({
            'from': faucet_address,
            'to': target,
            'gas': 21000,
            'value': 1 * denoms.ether,
        })
        custom_token.functions.transfer(
            target,
            10000,
        ).transact({'from': faucet_address})
    return f
