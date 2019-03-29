"""
The tests in this module mock Capacity Updates and call on_pfs_update().

The Capacity Updates show different correct and incorrect values to test all edge cases
"""

from typing import List

import pytest
from eth_utils import decode_hex

from pathfinding_service import PathfindingService
from pathfinding_service.exceptions import InvalidCapacityUpdate
from pathfinding_service.model import TokenNetwork
from raiden.constants import UINT256_MAX
from raiden.messages import UpdatePFS
from raiden.utils import CanonicalIdentifier
from raiden.utils.typing import (
    ChainID,
    ChannelID,
    Nonce,
    Signature,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_libs.types import Address

DEFAULT_TOKEN_NETWORK_ADDRESS = Address('0x6e46B62a245D9EE7758B8DdCCDD1B85fF56B9Bc9')
DEFAULT_TOKEN_NETWORK_ADDRESS_BYTES = TokenNetworkAddress(
    decode_hex(DEFAULT_TOKEN_NETWORK_ADDRESS),
)
DEFAULT_TOKEN_ADDRESS = Address('0x44Ac22fd9672cC559Ab171603D474cEA8a2D7b4D')


def get_updatepfs_message(
        updating_participant: Address,
        other_participant: Address,
        chain_identifier=ChainID(1),
        channel_identifier=ChannelID(0),
        token_network_address: TokenNetworkAddress = DEFAULT_TOKEN_NETWORK_ADDRESS_BYTES,
        updating_nonce=Nonce(1),
        other_nonce=Nonce(0),
        updating_capacity=TokenAmount(90),
        other_capacity=TokenAmount(110),
        reveal_timeout: int = 2,
        signature=Signature(bytes()),
) -> UpdatePFS:
    return UpdatePFS(
        canonical_identifier=CanonicalIdentifier(
            chain_identifier=chain_identifier,
            channel_identifier=channel_identifier,
            token_network_address=token_network_address,
        ),
        updating_participant=decode_hex(updating_participant),
        other_participant=decode_hex(other_participant),
        updating_nonce=updating_nonce,
        other_nonce=other_nonce,
        updating_capacity=updating_capacity,
        other_capacity=other_capacity,
        reveal_timeout=reveal_timeout,
        signature=signature,
    )


def test_pfs_rejects_capacity_update_with_wrong_chain_id(
    addresses: List[Address],
    pathfinding_service_mocked_listeners: PathfindingService,
):

    message = get_updatepfs_message(
        chain_identifier=ChainID(121212),
        updating_participant=addresses[0],
        other_participant=addresses[1],
    )

    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_mocked_listeners.on_pfs_update(message)
    assert 'unknown chain identifier' in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_wrong_token_network_address(
    addresses: List[Address],
    pathfinding_service_mocked_listeners: PathfindingService,
):
    pathfinding_service_mocked_listeners.chain_id = ChainID(1)

    token_network = TokenNetwork(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        token_address=DEFAULT_TOKEN_ADDRESS,
    )

    pathfinding_service_mocked_listeners.token_networks[
        token_network.address] = token_network

    message = get_updatepfs_message(
        token_network_address=TokenNetworkAddress(decode_hex('0x' + '1' * 40)),
        updating_participant=addresses[0],
        other_participant=addresses[1],
    )

    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_mocked_listeners.on_pfs_update(message)
    assert 'unknown token network' in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_wrong_channel_identifier(
        addresses: List[Address],
        pathfinding_service_mocked_listeners: PathfindingService,
):
    pathfinding_service_mocked_listeners.chain_id = ChainID(1)

    token_network = TokenNetwork(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        token_address=DEFAULT_TOKEN_ADDRESS,
    )

    pathfinding_service_mocked_listeners.token_networks[
        token_network.address] = token_network

    token_network.handle_channel_opened_event(
        channel_identifier=ChannelID(0),
        participant1=addresses[0],
        participant2=addresses[1],
        settle_timeout=15,
    )

    # Check that the new channel has id == 0
    assert token_network.channel_id_to_addresses[ChannelID(0)] == (
        addresses[0],
        addresses[1],
    )

    message = get_updatepfs_message(
        channel_identifier=ChannelID(35),
        updating_participant=addresses[0],
        other_participant=addresses[1],
    )

    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_mocked_listeners.on_pfs_update(message)
    assert 'unknown channel identifier in token network' in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_impossible_updating_capacity(
        addresses: List[Address],
        pathfinding_service_mocked_listeners: PathfindingService,
):
    pathfinding_service_mocked_listeners.chain_id = ChainID(1)

    token_network = TokenNetwork(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        token_address=DEFAULT_TOKEN_ADDRESS,
    )

    pathfinding_service_mocked_listeners.token_networks[
        token_network.address] = token_network

    token_network.handle_channel_opened_event(
        channel_identifier=ChannelID(0),
        participant1=addresses[0],
        participant2=addresses[1],
        settle_timeout=15,
    )

    token_network.handle_channel_new_deposit_event(
        channel_identifier=ChannelID(0),
        receiver=addresses[0],
        total_deposit=100,
    )

    token_network.handle_channel_new_deposit_event(
        channel_identifier=ChannelID(0),
        receiver=addresses[1],
        total_deposit=100,
    )

    # Check that the new channel has id == 0
    assert token_network.channel_id_to_addresses[ChannelID(0)] == (
        addresses[0],
        addresses[1],
    )

    message = get_updatepfs_message(
        updating_participant=addresses[0],
        other_participant=addresses[1],
        updating_capacity=TokenAmount(UINT256_MAX + 1),
    )

    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_mocked_listeners.on_pfs_update(message)
    assert 'with impossible updating_capacity' in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_impossible_other_capacity(
        addresses: List[Address],
        pathfinding_service_mocked_listeners: PathfindingService,
):
    pathfinding_service_mocked_listeners.chain_id = ChainID(1)

    token_network = TokenNetwork(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        token_address=DEFAULT_TOKEN_ADDRESS,
    )

    pathfinding_service_mocked_listeners.token_networks[
        token_network.address] = token_network

    token_network.handle_channel_opened_event(
        channel_identifier=ChannelID(0),
        participant1=addresses[0],
        participant2=addresses[1],
        settle_timeout=15,
    )

    token_network.handle_channel_new_deposit_event(
        channel_identifier=ChannelID(0),
        receiver=addresses[0],
        total_deposit=100,
    )

    token_network.handle_channel_new_deposit_event(
        channel_identifier=ChannelID(0),
        receiver=addresses[1],
        total_deposit=100,
    )

    # Check that the new channel has id == 0
    assert token_network.channel_id_to_addresses[ChannelID(0)] == (
        addresses[0],
        addresses[1],
    )

    message = get_updatepfs_message(
        updating_participant=addresses[0],
        other_participant=addresses[1],
        other_capacity=TokenAmount(UINT256_MAX + 1),
    )

    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_mocked_listeners.on_pfs_update(message)
    assert 'with impossible other_capacity' in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_wrong_updating_participant(
        addresses: List[Address],
        pathfinding_service_mocked_listeners: PathfindingService,
):
    pathfinding_service_mocked_listeners.chain_id = ChainID(1)

    token_network = TokenNetwork(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        token_address=DEFAULT_TOKEN_ADDRESS,
    )

    pathfinding_service_mocked_listeners.token_networks[
        token_network.address] = token_network

    token_network.handle_channel_opened_event(
        channel_identifier=ChannelID(0),
        participant1=addresses[0],
        participant2=addresses[1],
        settle_timeout=15,
    )

    token_network.handle_channel_new_deposit_event(
        channel_identifier=ChannelID(0),
        receiver=addresses[0],
        total_deposit=100,
    )

    token_network.handle_channel_new_deposit_event(
        channel_identifier=ChannelID(0),
        receiver=addresses[1],
        total_deposit=100,
    )

    # Check that the new channel has id == 0
    assert token_network.channel_id_to_addresses[ChannelID(0)] == (
        addresses[0],
        addresses[1],
    )

    message = get_updatepfs_message(
        updating_participant=addresses[2],
        other_participant=addresses[1],
    )

    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_mocked_listeners.on_pfs_update(message)
    assert 'Sender of Capacity Update does not match' in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_wrong_other_participant(
        addresses: List[Address],
        pathfinding_service_mocked_listeners: PathfindingService,
):
    pathfinding_service_mocked_listeners.chain_id = ChainID(1)

    token_network = TokenNetwork(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        token_address=DEFAULT_TOKEN_ADDRESS,
    )

    pathfinding_service_mocked_listeners.token_networks[
        token_network.address] = token_network

    token_network.handle_channel_opened_event(
        channel_identifier=ChannelID(0),
        participant1=addresses[0],
        participant2=addresses[1],
        settle_timeout=15,
    )

    token_network.handle_channel_new_deposit_event(
        channel_identifier=ChannelID(0),
        receiver=addresses[0],
        total_deposit=100,
    )

    token_network.handle_channel_new_deposit_event(
        channel_identifier=ChannelID(0),
        receiver=addresses[1],
        total_deposit=100,
    )

    # Check that the new channel has id == 0
    assert token_network.channel_id_to_addresses[ChannelID(0)] == (
        addresses[0],
        addresses[1],
    )

    message = get_updatepfs_message(
        updating_participant=addresses[0],
        other_participant=addresses[2],
    )

    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_mocked_listeners.on_pfs_update(message)
    assert 'Other Participant of Capacity Update does not match' in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_wrong_nonces(
        addresses: List[Address],
        pathfinding_service_mocked_listeners: PathfindingService,
):
    pathfinding_service_mocked_listeners.chain_id = ChainID(1)

    token_network = TokenNetwork(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        token_address=DEFAULT_TOKEN_ADDRESS,
    )

    pathfinding_service_mocked_listeners.token_networks[
        token_network.address] = token_network

    token_network.handle_channel_opened_event(
        channel_identifier=ChannelID(0),
        participant1=addresses[0],
        participant2=addresses[1],
        settle_timeout=15,
    )

    token_network.handle_channel_new_deposit_event(
        channel_identifier=ChannelID(0),
        receiver=addresses[0],
        total_deposit=100,
    )

    token_network.handle_channel_new_deposit_event(
        channel_identifier=ChannelID(0),
        receiver=addresses[1],
        total_deposit=100,
    )

    # Check that the new channel has id == 0
    assert token_network.channel_id_to_addresses[ChannelID(0)] == (
        addresses[0],
        addresses[1],
    )

    message = get_updatepfs_message(
        updating_participant=addresses[0],
        other_participant=addresses[1],
    )

    # Check first capacity update succeeded
    pathfinding_service_mocked_listeners.on_pfs_update(message)
    view_to_partner, view_from_partner = token_network.get_channel_views_for_partner(
        channel_identifier=ChannelID(0),
        updating_participant=addresses[0],
        other_participant=addresses[1],
    )
    assert view_to_partner.capacity == 90
    assert view_to_partner.update_nonce == 1
    assert view_from_partner.capacity == 110
    assert view_from_partner.update_nonce == 0

    # Send the same Capacity Update again - leads to an exception
    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_mocked_listeners.on_pfs_update(message)
    assert 'Capacity Update already received' in str(exinfo.value)
