import random
from typing import Callable

import pytest
from eth_utils import denoms, is_address, encode_hex

from raiden_libs.utils import (
    sha3,
    private_key_to_address,
    UINT64_MAX,
    UINT192_MAX,
    UINT256_MAX,
)
from raiden_libs.messages import BalanceProof, MonitorRequest
from raiden_libs.utils.signing import eth_sign
from raiden_libs.types import Address, ChannelIdentifier


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


@pytest.fixture
def get_random_monitor_request(get_random_bp, get_random_address, get_random_privkey):
    def f():
        balance_proof = get_random_bp()
        privkey = get_random_privkey()
        privkey_non_closing = get_random_privkey()
        balance_proof.signature = encode_hex(eth_sign(privkey, balance_proof.serialize_bin()))
        non_closing_signature = encode_hex(
            eth_sign(privkey_non_closing, balance_proof.serialize_bin()),
        )

        monitor_request = MonitorRequest(
            balance_proof,
            non_closing_signature,
            reward_amount=random.randint(0, UINT192_MAX),
            monitor_address=get_random_address(),
        )
        monitor_request.reward_proof_signature = encode_hex(
            eth_sign(privkey, monitor_request.serialize_reward_proof()),
        )
        return monitor_request
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
