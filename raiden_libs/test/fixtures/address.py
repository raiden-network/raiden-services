import random
from typing import Callable

import pytest
from sha3 import keccak_256
from eth_utils import denoms, is_address, encode_hex

from raiden_libs.utils import (
    private_key_to_address,
    UINT64_MAX,
    UINT192_MAX,
    UINT256_MAX
)
from raiden_libs.messages import BalanceProof, MonitorRequest
from raiden_libs.utils.signing import sign_data
from raiden_libs.types import Address, ChannelIdentifier


@pytest.fixture
def get_random_privkey() -> Callable:
    """Returns a random private key"""
    return lambda: "0x%064x" % random.randint(
        1,
        UINT256_MAX
    )


@pytest.fixture
def get_random_address(get_random_privkey) -> Callable:
    """Returns a random valid ethereum address"""
    def f():
        return private_key_to_address(get_random_privkey())
    return f


@pytest.fixture
def get_random_bp(get_random_address) -> Callable:
    """Returns a balance proof filled in with a random value"""
    def f(
        channel_id: ChannelIdentifier = None,
        contract_address: Address = None
    ):
        contract_address = contract_address or Address(get_random_address())
        channel_id = channel_id or ChannelIdentifier(random.randint(0, UINT64_MAX))
        msg = BalanceProof(channel_id, contract_address)
        msg.nonce = random.randint(0, UINT64_MAX)
        msg.transferred_amount = random.randint(0, UINT64_MAX)  # actual maximum is uint256
        # locksroot and extra_hash are 32bytes each
        hash_data = '%d' % random.randint(0, UINT64_MAX)
        msg.locksroot = keccak_256(hash_data.encode()).hexdigest()
        hash_data = '%d' % random.randint(0, UINT64_MAX)
        msg.extra_hash = keccak_256(hash_data.encode()).hexdigest()
        return msg
    return f


@pytest.fixture
def get_random_monitor_request(get_random_bp, get_random_address, get_random_privkey):
    def f():
        bp = get_random_bp()
        privkey = get_random_privkey()
        bp.signature = encode_hex(sign_data(privkey, bp.serialize_bin()))
        mr = MonitorRequest(
            bp.channel_id,
            bp.nonce,
            bp.transferred_amount,
            bp.locksroot,
            bp.extra_hash,
            bp.signature,
            reward_sender_address=get_random_address(),
            reward_amount=random.randint(0, UINT192_MAX),
            token_network_address=get_random_address(),
            chain_id=random.randint(0, UINT256_MAX),
            monitor_address=get_random_address()
        )
        mr.reward_proof_signature = encode_hex(sign_data(privkey, mr.serialize_reward_proof()))
        return mr
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
    standard_token_contract,
    faucet_address,
):
    """Send some tokens and eth to specified address."""
    def f(target: str):
        assert is_address(target)
        ethereum_tester.send_transaction({
            'from': faucet_address,
            'to': target,
            'gas': 21000,
            'value': 1 * denoms.ether
        })
        standard_token_contract.functions.transfer(
            target,
            10000
        ).transact({'from': faucet_address})
    return f
