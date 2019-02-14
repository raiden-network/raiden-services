import random
from typing import Callable

import pytest
from eth_utils import encode_hex

from monitoring_service.states import (
    Channel,
    HashedBalanceProof,
    OnChainUpdateStatus,
    UnsignedMonitorRequest,
)
from raiden_contracts.constants import ChannelState
from raiden_libs.types import ChannelIdentifier
from raiden_libs.utils import UINT64_MAX, UINT256_MAX, private_key_to_address, sha3


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

        bp = HashedBalanceProof(  # type: ignore
            channel_identifier=channel_identifier,
            token_network_address=contract_address,
            chain_id=chain_id,
            balance_hash=balance_hash,
            nonce=nonce,
            additional_hash=additional_hash,
            priv_key=privkey,
        )
        monitor_request = UnsignedMonitorRequest.from_balance_proof(
            bp,
            reward_amount=0,
        ).sign(privkey_non_closing)
        return monitor_request, privkey, privkey_non_closing
    return f


def test_monitor_request_properties(get_random_monitor_request):
    request, p1, p2 = get_random_monitor_request()

    assert request.signer == private_key_to_address(p1)
    assert request.non_closing_signer == private_key_to_address(p2)
    assert request.reward_proof_signer == private_key_to_address(p2)


def test_save_and_load_mr(get_random_monitor_request, ms_database):
    request, _, _ = get_random_monitor_request()
    ms_database.upsert_monitor_request(request)
    loaded_request = ms_database.get_monitor_request(
        token_network_address=request.token_network_address,
        channel_id=request.channel_identifier,
        non_closing_signer=request.non_closing_signer,
    )
    assert loaded_request == request


def test_save_and_load_channel(ms_database, get_random_address):
    token_network_address = get_random_address()
    ms_database.conn.execute(
        "INSERT INTO token_network (address) VALUES (?)",
        [token_network_address],
    )
    for update_status in [
        None,
        OnChainUpdateStatus(
            update_sender_address=get_random_address(),
            nonce=random.randint(0, UINT256_MAX),
        ),
    ]:
        channel = Channel(
            token_network_address=token_network_address,
            identifier=random.randint(0, UINT256_MAX),
            participant1=get_random_address(),
            participant2=get_random_address(),
            settle_timeout=random.randint(0, UINT256_MAX),
            state=random.choice(list(ChannelState)),
            closing_block=random.randint(0, UINT256_MAX),
            closing_participant=get_random_address(),
            closing_tx_hash='%d' % random.randint(0, UINT64_MAX),
            claim_tx_hash='%d' % random.randint(0, UINT64_MAX),
            update_status=update_status,
        )
        ms_database.upsert_channel(channel)
        loaded_channel = ms_database.get_channel(
            token_network_address=channel.token_network_address,
            channel_id=channel.identifier,
        )
        assert loaded_channel == channel
