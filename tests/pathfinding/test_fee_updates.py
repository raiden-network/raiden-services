"""
The tests in this module mock Fee Updates and call on_fee_update().

The Fee Updates show different correct and incorrect values to test all edge cases
"""
from datetime import datetime, timezone

import pytest
from eth_utils import decode_hex, to_canonical_address

from pathfinding_service.exceptions import InvalidFeeUpdate
from pathfinding_service.model import TokenNetwork
from pathfinding_service.service import DeferMessage, PathfindingService
from raiden.constants import EMPTY_SIGNATURE
from raiden.messages.path_finding_service import PFSFeeUpdate
from raiden.transfer.identifiers import CanonicalIdentifier
from raiden.transfer.mediated_transfer.mediation_fee import FeeScheduleState
from raiden.utils.signer import LocalSigner
from raiden.utils.typing import (
    Address,
    BlockTimeout,
    ChainID,
    ChannelID,
    FeeAmount,
    ProportionalFeeAmount,
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
        settle_timeout=BlockTimeout(15),
    )

    # Check that the new channel has id == 0
    assert set(token_network.channel_id_to_addresses[DEFAULT_CHANNEL_ID]) == {
        PRIVATE_KEY_1_ADDRESS,
        PRIVATE_KEY_2_ADDRESS,
    }

    return token_network


def get_fee_update_message(  # pylint: disable=too-many-arguments
    updating_participant: Address,
    chain_id=ChainID(61),
    channel_identifier=DEFAULT_CHANNEL_ID,
    token_network_address: TokenNetworkAddress = DEFAULT_TOKEN_NETWORK_ADDRESS,
    fee_schedule: FeeScheduleState = FeeScheduleState(
        cap_fees=True, flat=FeeAmount(1), proportional=ProportionalFeeAmount(1)
    ),
    timestamp: datetime = datetime.utcnow(),
    privkey_signer: bytes = PRIVATE_KEY_1,
) -> PFSFeeUpdate:
    fee_message = PFSFeeUpdate(
        canonical_identifier=CanonicalIdentifier(
            chain_identifier=chain_id,
            channel_identifier=channel_identifier,
            token_network_address=token_network_address,
        ),
        updating_participant=updating_participant,
        fee_schedule=fee_schedule,
        timestamp=timestamp,
        signature=EMPTY_SIGNATURE,
    )

    fee_message.sign(LocalSigner(privkey_signer))

    return fee_message


def test_pfs_rejects_fee_update_with_wrong_chain_id(
    pathfinding_service_web3_mock: PathfindingService,
):
    setup_channel(pathfinding_service_web3_mock)

    message = get_fee_update_message(
        chain_id=ChainID(121212),
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
    )

    with pytest.raises(InvalidFeeUpdate) as exinfo:
        pathfinding_service_web3_mock.on_fee_update(message)
    assert "unknown chain identifier" in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_wrong_token_network_address(
    pathfinding_service_web3_mock: PathfindingService,
):
    setup_channel(pathfinding_service_web3_mock)

    message = get_fee_update_message(
        token_network_address=TokenNetworkAddress(to_canonical_address("0x" + "1" * 40)),
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
    )

    with pytest.raises(InvalidFeeUpdate) as exinfo:
        pathfinding_service_web3_mock.on_fee_update(message)
    assert "unknown token network" in str(exinfo.value)


def test_pfs_rejects_capacity_update_with_wrong_channel_identifier(
    pathfinding_service_web3_mock: PathfindingService,
):
    setup_channel(pathfinding_service_web3_mock)

    message = get_fee_update_message(
        channel_identifier=ChannelID(35),
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
    )

    with pytest.raises(DeferMessage):
        pathfinding_service_web3_mock.on_fee_update(message)


def test_pfs_rejects_fee_update_with_incorrect_signature(
    pathfinding_service_web3_mock: PathfindingService,
):
    setup_channel(pathfinding_service_web3_mock)

    message = get_fee_update_message(
        updating_participant=PRIVATE_KEY_1_ADDRESS, privkey_signer=PRIVATE_KEY_3
    )

    with pytest.raises(InvalidFeeUpdate) as exinfo:
        pathfinding_service_web3_mock.on_fee_update(message)
    assert "Fee Update not signed correctly" in str(exinfo.value)


def test_pfs_rejects_fee_update_with_incorrect_timestamp(
    pathfinding_service_web3_mock: PathfindingService,
):
    setup_channel(pathfinding_service_web3_mock)

    message = get_fee_update_message(
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
        timestamp=datetime.now(tz=timezone.utc),
    )

    with pytest.raises(InvalidFeeUpdate) as exinfo:
        pathfinding_service_web3_mock.on_fee_update(message)
    assert "Fee Update should not contain timezone" in str(exinfo.value)

    valid_message = get_fee_update_message(
        updating_participant=PRIVATE_KEY_1_ADDRESS,
        privkey_signer=PRIVATE_KEY_1,
        timestamp=datetime.utcnow(),
    )
    pathfinding_service_web3_mock.on_fee_update(valid_message)
