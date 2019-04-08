from typing import List

from pathfinding_service.model import TokenNetwork
from raiden.utils.typing import ChannelID
from raiden_libs.types import Address


def test_tn_idempotency_of_channel_openings(
    token_network_model: TokenNetwork, addresses: List[Address]
):
    # create same channel 5 times
    for _ in range(5):
        token_network_model.handle_channel_opened_event(
            channel_identifier=ChannelID(1),
            participant1=addresses[0],
            participant2=addresses[1],
            settle_timeout=15,
        )
    # there should only be one channel
    assert len(token_network_model.channel_id_to_addresses) == 1

    # now close the channel
    token_network_model.handle_channel_closed_event(channel_identifier=ChannelID(1))

    # there should be no channels
    assert len(token_network_model.channel_id_to_addresses) == 0


def test_tn_multiple_channels_for_two_participants_opened(
    token_network_model: TokenNetwork, addresses: List[Address]
):
    token_network_model.handle_channel_opened_event(
        channel_identifier=ChannelID(1),
        participant1=addresses[0],
        participant2=addresses[1],
        settle_timeout=15,
    )
    token_network_model.handle_channel_opened_event(
        channel_identifier=ChannelID(2),
        participant1=addresses[0],
        participant2=addresses[1],
        settle_timeout=15,
    )

    # now there should be two channels
    assert len(token_network_model.channel_id_to_addresses) == 2

    # now close one channel
    token_network_model.handle_channel_closed_event(channel_identifier=ChannelID(1))

    # there should be one channel left
    assert len(token_network_model.channel_id_to_addresses) == 1
