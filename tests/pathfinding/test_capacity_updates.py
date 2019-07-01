"""
The tests in this module mock Capacity Updates and call on_capacity_update().

The Capacity Updates show different correct and incorrect values to test all edge cases
"""
from unittest.mock import call

import pytest
from eth_utils import decode_hex

from pathfinding_service.exceptions import InvalidCapacityUpdate
from pathfinding_service.model import TokenNetwork
from pathfinding_service.service import DeferMessage, PathfindingService
from raiden.constants import EMPTY_SIGNATURE, UINT256_MAX
from raiden.messages import PFSCapacityUpdate
from raiden.transfer.identifiers import CanonicalIdentifier
from raiden.utils.signer import LocalSigner
from raiden.utils.typing import (
    Address,
    ChainID,
    ChannelID,
    Nonce,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_libs.utils import private_key_to_address

DEFAULT_TOKEN_NETWORK_ADDRESS = TokenNetworkAddress(
    decode_hex("0x6e46B62a245D9EE7758B8DdCCDD1B85fF56B9Bc9")
)
PRIVATE_KEY_1 = bytes([1] * 32)
PRIVATE_KEY_1_ADDRESS = private_key_to_address(PRIVATE_KEY_1)
PRIVATE_KEY_2 = bytes([2] * 32)
PRIVATE_KEY_2_ADDRESS = private_key_to_address(PRIVATE_KEY_2)
PRIVATE_KEY_3 = bytes([3] * 32)
PRIVATE_KEY_3_ADDRESS = private_key_to_address(PRIVATE_KEY_3)
DEFAULT_CHANNEL_ID = ChannelID(0)


def setup_channel(service: PathfindingService) -> TokenNetwork:
    token_network = TokenNetwork(token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS)
    service.token_networks[token_network.address] = token_network

    token_network.handle_channel_opened_event(
        channel_identifier=DEFAULT_CHANNEL_ID,
        participant1=PRIVATE_KEY_1_ADDRESS,
        participant2=PRIVATE_KEY_2_ADDRESS,
        settle_timeout=15,
    )

    # Check that the new channel has id == 0
    assert token_network.channel_id_to_addresses[DEFAULT_CHANNEL_ID] == (
        PRIVATE_KEY_1_ADDRESS,
        PRIVATE_KEY_2_ADDRESS,
    )

    return token_network


def setup_channel_with_deposits(service: PathfindingService) -> TokenNetwork:
    token_network = setup_channel(service)

    token_network.handle_channel_new_deposit_event(
        channel_identifier=DEFAULT_CHANNEL_ID,
        receiver=PRIVATE_KEY_1_ADDRESS,
        total_deposit=TokenAmount(100),
    )
    token_network.handle_channel_new_deposit_event(
        channel_identifier=DEFAULT_CHANNEL_ID,
        receiver=PRIVATE_KEY_2_ADDRESS,
        total_deposit=TokenAmount(100),
    )
    return token_network


def get_updatepfs_message(  # pylint: disable=too-many-arguments
    updating_participant: Address,
    other_participant: Address,
    chain_identifier=ChainID(1),
    channel_identifier=DEFAULT_CHANNEL_ID,
    token_network_address: TokenNetworkAddress = DEFAULT_TOKEN_NETWORK_ADDRESS,
    updating_nonce=Nonce(1),
    other_nonce=Nonce(0),
    updating_capacity=TokenAmount(90),
    other_capacity=TokenAmount(110),
    reveal_timeout: int = 2,
    privkey_signer: bytes = PRIVATE_KEY_1,
) -> PFSCapacityUpdate:
    updatepfs_message = PFSCapacityUpdate(
        canonical_identifier=CanonicalIdentifier(
            chain_identifier=chain_identifier,
            channel_identifier=channel_identifier,
            token_network_address=token_network_address,
        ),
        updating_participant=updating_participant,
        other_participant=other_participant,
        updating_nonce=updating_nonce,
        other_nonce=other_nonce,
        updating_capacity=updating_capacity,
        other_capacity=other_capacity,
        reveal_timeout=reveal_timeout,
        signature=EMPTY_SIGNATURE,
    )

    updatepfs_message.sign(LocalSigner(privkey_signer))

    return updatepfs_message


def test_pfs_rejects_capacity_update_with_wrong_chain_id(
    pathfinding_service_web3_mock: PathfindingService
):
    setup_channel(pathfinding_service_web3_mock)

    message = get_updatepfs_message(
        chain_identifier=ChainID(121212),
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        other_participant=PRIVATE_KEY_2_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
    )

    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_web3_mock.on_capacity_update(message)
    assert "unknown chain identifier" in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_wrong_token_network_address(
    pathfinding_service_web3_mock: PathfindingService,
):
    setup_channel(pathfinding_service_web3_mock)

    message = get_updatepfs_message(
        token_network_address=TokenNetworkAddress(decode_hex("0x" + "1" * 40)),
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        other_participant=PRIVATE_KEY_2_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
    )

    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_web3_mock.on_capacity_update(message)
    assert "unknown token network" in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_wrong_channel_identifier(
    pathfinding_service_web3_mock: PathfindingService
):
    setup_channel(pathfinding_service_web3_mock)

    message = get_updatepfs_message(
        channel_identifier=ChannelID(35),
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        other_participant=PRIVATE_KEY_2_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
    )

    with pytest.raises(DeferMessage):
        pathfinding_service_web3_mock.on_capacity_update(message)


def test_pfs_rejects_capacity_update_with_impossible_updating_capacity(
    pathfinding_service_web3_mock: PathfindingService,
):
    setup_channel_with_deposits(pathfinding_service_web3_mock)

    message = get_updatepfs_message(
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        other_participant=PRIVATE_KEY_2_ADDRESS,
        updating_capacity=TokenAmount(UINT256_MAX),
        privkey_signer=PRIVATE_KEY_1,
    )
    message.updating_capacity = TokenAmount(UINT256_MAX + 1)

    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_web3_mock.on_capacity_update(message)
    assert "with impossible updating_capacity" in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_impossible_other_capacity(
    pathfinding_service_web3_mock: PathfindingService,
):
    setup_channel_with_deposits(pathfinding_service_web3_mock)

    message = get_updatepfs_message(
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        other_participant=PRIVATE_KEY_2_ADDRESS,
        other_capacity=TokenAmount(UINT256_MAX),
        privkey_signer=PRIVATE_KEY_1,
    )
    message.other_capacity = TokenAmount(UINT256_MAX + 1)

    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_web3_mock.on_capacity_update(message)
    assert "with impossible other_capacity" in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_wrong_updating_participant(
    pathfinding_service_web3_mock: PathfindingService,
):
    setup_channel_with_deposits(pathfinding_service_web3_mock)

    message = get_updatepfs_message(
        updating_participant=PRIVATE_KEY_3_ADDRESS,
        other_participant=PRIVATE_KEY_2_ADDRESS,
        privkey_signer=PRIVATE_KEY_3,
    )

    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_web3_mock.on_capacity_update(message)
    assert "Sender of Capacity Update does not match" in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_wrong_other_participant(
    pathfinding_service_web3_mock: PathfindingService
):
    setup_channel_with_deposits(pathfinding_service_web3_mock)

    message = get_updatepfs_message(
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        other_participant=PRIVATE_KEY_3_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
    )

    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_web3_mock.on_capacity_update(message)
    assert "Other Participant of Capacity Update does not match" in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_incorrect_signature(
    pathfinding_service_web3_mock: PathfindingService
):
    setup_channel_with_deposits(pathfinding_service_web3_mock)

    message = get_updatepfs_message(
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        other_participant=PRIVATE_KEY_2_ADDRESS,
        privkey_signer=PRIVATE_KEY_3,
    )

    with pytest.raises(InvalidCapacityUpdate) as exinfo:
        pathfinding_service_web3_mock.on_capacity_update(message)
    assert "Capacity Update not signed correctly" in str(exinfo.value)


def test_pfs_edge_case_capacity_updates_before_deposit(
    pathfinding_service_web3_mock: PathfindingService
):
    token_network = setup_channel(pathfinding_service_web3_mock)

    view_to_partner, view_from_partner = token_network.get_channel_views_for_partner(
        updating_participant=PRIVATE_KEY_1_ADDRESS, other_participant=PRIVATE_KEY_2_ADDRESS
    )

    token_network.handle_channel_new_deposit_event(
        channel_identifier=DEFAULT_CHANNEL_ID,
        receiver=PRIVATE_KEY_1_ADDRESS,
        total_deposit=TokenAmount(100),
    )

    # So te PFS did not receive a deposit for P2.
    assert view_to_partner.capacity == 100
    assert view_from_partner.capacity == 0

    message1 = get_updatepfs_message(
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        other_participant=PRIVATE_KEY_2_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
        updating_capacity=90,
        other_capacity=10,
    )
    message2 = get_updatepfs_message(
        updating_participant=PRIVATE_KEY_2_ADDRESS,
        other_participant=PRIVATE_KEY_1_ADDRESS,
        privkey_signer=PRIVATE_KEY_2,
        updating_capacity=10,
        other_capacity=90,
    )

    # we expect no capacity at all since we don't know anything from P2
    pathfinding_service_web3_mock.on_capacity_update(message1)
    assert view_to_partner.capacity == 0
    assert view_from_partner.capacity == 0

    # we expect now the capacity as stated in both consistent messages
    pathfinding_service_web3_mock.on_capacity_update(message2)
    assert view_to_partner.capacity == 90
    assert view_from_partner.capacity == 10

    # now the pfs gets the deposit message from P2 and we expect the capacity of P2 to be 110
    token_network.handle_channel_new_deposit_event(
        channel_identifier=DEFAULT_CHANNEL_ID,
        receiver=PRIVATE_KEY_2_ADDRESS,
        total_deposit=TokenAmount(100),
    )
    assert view_to_partner.capacity == 90
    assert view_from_partner.capacity == 110

    # Check that presence of these addresses is followed
    pathfinding_service_web3_mock.matrix_listener.follow_address_presence.assert_has_calls(  # type: ignore # noqa
        [call(PRIVATE_KEY_1_ADDRESS, refresh=True), call(PRIVATE_KEY_2_ADDRESS, refresh=True)]
    )


def test_pfs_min_calculation_with_capacity_updates(
    pathfinding_service_web3_mock: PathfindingService
):
    token_network = setup_channel_with_deposits(pathfinding_service_web3_mock)

    view_to_partner, view_from_partner = token_network.get_channel_views_for_partner(
        updating_participant=PRIVATE_KEY_1_ADDRESS, other_participant=PRIVATE_KEY_2_ADDRESS
    )

    # Assert initial capacity with no Capacity Updates
    assert view_to_partner.capacity == 100
    assert view_from_partner.capacity == 100

    message1 = get_updatepfs_message(
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        other_participant=PRIVATE_KEY_2_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
        updating_capacity=90,
        other_capacity=110,
    )

    pathfinding_service_web3_mock.on_capacity_update(message1)

    # Now the channel capacities are set to 0, since only P1 sent an update
    assert view_to_partner.capacity == 0
    assert view_from_partner.capacity == 0

    # We need two Capacity Updates, one from each side to set the capacities due to min calculation
    message2 = get_updatepfs_message(
        updating_participant=PRIVATE_KEY_2_ADDRESS,
        other_participant=PRIVATE_KEY_1_ADDRESS,
        privkey_signer=PRIVATE_KEY_2,
        updating_capacity=110,
        other_capacity=90,
    )

    pathfinding_service_web3_mock.on_capacity_update(message2)

    # Now after both participants have sent Capacity Updates, we have the correct capacities
    assert view_to_partner.capacity == 90
    assert view_from_partner.capacity == 110

    # Now P1 sends the same update again, the capacities should not change (no need for nonces)
    pathfinding_service_web3_mock.on_capacity_update(message1)
    assert view_to_partner.capacity == 90
    assert view_from_partner.capacity == 110

    # Now P1 tries to cheat and lies about his own capacity (10000) to mediate more
    message3 = get_updatepfs_message(
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        other_participant=PRIVATE_KEY_2_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
        updating_capacity=10000,
        other_capacity=110,
    )
    pathfinding_service_web3_mock.on_capacity_update(message3)

    # The capacities should be calculated out of the minimum of the two capacity updates,
    # so stay the same
    assert view_to_partner.capacity == 90
    assert view_from_partner.capacity == 110

    # Now P1 tries to cheat and lies about his partner's capacity (0) to block him
    message4 = get_updatepfs_message(
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        other_participant=PRIVATE_KEY_2_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
        updating_capacity=90,
        other_capacity=0,
    )
    pathfinding_service_web3_mock.on_capacity_update(message4)

    # The capacities should be calculated out of the minimum of the two capacity updates,
    #  he can block his partner
    assert view_to_partner.capacity == 90
    assert view_from_partner.capacity == 0

    # Now P1 tries to cheat and lies about his partner's capacity (10000) for no obvious reason
    message4 = get_updatepfs_message(
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        other_participant=PRIVATE_KEY_2_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
        updating_capacity=90,
        other_capacity=10000,
    )
    pathfinding_service_web3_mock.on_capacity_update(message4)

    # The capacities should be calculated out of the minimum of the two capacity updates
    assert view_to_partner.capacity == 90
    assert view_from_partner.capacity == 110

    # Test if new deposits work as expected, so P1 deposits 100 new tokens
    # (total deposit 200, but capacity must be 190)

    token_network.handle_channel_new_deposit_event(
        channel_identifier=DEFAULT_CHANNEL_ID,
        receiver=PRIVATE_KEY_1_ADDRESS,
        total_deposit=TokenAmount(200),
    )
    assert view_to_partner.capacity == 190
    assert view_from_partner.capacity == 110
