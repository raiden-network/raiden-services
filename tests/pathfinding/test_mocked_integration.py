"""
The tests in this module mock events creation by using a mock blockchain listener.

This makes them a lot faster than using full blockchain based approach and they should
be used most of the time to keep test times short.
"""
from typing import List

from eth_utils import decode_hex

from pathfinding_service import PathfindingService
from pathfinding_service.model import TokenNetwork
from raiden_libs.types import Address, ChannelIdentifier


def test_pfs_with_mocked_events(
    token_network_model: TokenNetwork,
    addresses: List[Address],
    pathfinding_service_mocked_listeners: PathfindingService,
    channel_descriptions_case_1: List,
):
    registry_listener = pathfinding_service_mocked_listeners.token_network_registry_listener
    # assert registry_listener

    token_network_address = token_network_model.address

    # this is a new pathfinding service, there should be no token networks registered
    assert len(pathfinding_service_mocked_listeners.token_networks.keys()) == 0

    # emit a TokenNetworkCreated event
    registry_listener.emit_event(dict(
        event='TokenNetworkCreated',
        blockNumber=12,
        args=dict(
            token_network_address=token_network_address,
            token_address=token_network_model.token_address,
        ),
    ))

    # now there should be a token network registered
    assert token_network_address in pathfinding_service_mocked_listeners.token_networks
    token_network = pathfinding_service_mocked_listeners.token_networks[token_network_address]

    assert len(pathfinding_service_mocked_listeners.token_network_listeners) == 1
    network_listener = pathfinding_service_mocked_listeners.token_network_listeners[0]

    # Now initialize some channels in this network.
    for index, (
        p1_index,
        p1_deposit,
        _p1_transferred_amount,
        _p1_fee,
        p1_reveal_timeout,
        p2_index,
        p2_deposit,
        _p2_transferred_amount,
        _p2_fee,
        p2_reveal_timeout,
        settle_timeout,
    ) in enumerate(channel_descriptions_case_1):
        network_listener.emit_event(dict(
            address=token_network_address,
            event='ChannelOpened',
            args=dict(
                channel_identifier=index,
                participant1=addresses[p1_index],
                participant2=addresses[p2_index],
                settle_timeout=settle_timeout,
            ),
        ))

        network_listener.emit_event(dict(
            address=token_network_address,
            event='ChannelNewDeposit',
            args=dict(
                channel_identifier=index,
                participant=addresses[p1_index],
                total_deposit=p1_deposit,
            ),
        ))

        network_listener.emit_event(dict(
            address=token_network_address,
            event='ChannelNewDeposit',
            args=dict(
                channel_identifier=index,
                participant=addresses[p2_index],
                total_deposit=p2_deposit,
            ),
        ))
        token_network.handle_channel_balance_update_message(
            ChannelIdentifier(index),
            sender=addresses[p1_index],
            reveal_timeout=p1_reveal_timeout,
        )
        token_network.handle_channel_balance_update_message(
            ChannelIdentifier(index),
            sender=addresses[p2_index],
            reveal_timeout=p2_reveal_timeout,
        )

    # now there should be seven channels
    assert len(token_network.channel_id_to_addresses.keys()) == 7
    # check that deposits got registered
    for index, (
        p1_index,
        p1_deposit,
        _p1_transferred_amount,
        _p1_fee,
        _p1_reveal_timeout,
        p2_index,
        p2_deposit,
        _p2_transferred_amount,
        _p2_fee,
        _p2_reveal_timeout,
        _settle_timeout,
    ) in enumerate(channel_descriptions_case_1):
        p1, p2 = token_network.channel_id_to_addresses[ChannelIdentifier(index)]
        assert p1 == addresses[p1_index]
        assert p2 == addresses[p2_index]

        view1 = token_network.G[p1][p2]['view']
        view2 = token_network.G[p2][p1]['view']

        assert view1.deposit == p1_deposit
        assert view2.deposit == p2_deposit

    # check pathfinding without respecting transferred amounts
    # channel 2 <-> 3 has settle_timeout 3, so path is not eligible
    paths = token_network.get_paths(addresses[0], addresses[3], 10, 5)
    assert len(paths) == 2
    assert paths[0]['path'] == [addresses[0], addresses[1], addresses[4], addresses[3]]
    assert paths[1]['path'] == [
        addresses[0],
        addresses[2],
        addresses[1],
        addresses[4],
        addresses[3],
    ]

    # check pathfinding without having enough capacity on 2 <-> 0
    # so only 1 path is provided
    paths2 = token_network.get_paths(addresses[2], addresses[1], 85, 5)
    assert len(paths2) == 1
    assert paths2[0]['path'] == [addresses[2], addresses[1]]

    # wow close all channels
    for index, (
        p1_index,
        _p1_deposit,
        _p1_transferred_amount,
        _p1_fee,
        _p1_reveal_timeout,
        _p2_index,
        _p2_deposit,
        _p2_transferred_amount,
        _p2_fee,
        _p2_reveal_timeout,
        _settle_timeout,
    ) in enumerate(channel_descriptions_case_1):
        network_listener.emit_event(dict(
            address=token_network_address,
            event='ChannelClosed',
            args=dict(
                channel_identifier=index,
                closing_participant=addresses[p1_index],
            ),
        ))

    # there should be no channels
    assert len(token_network.channel_id_to_addresses.keys()) == 0


def test_pfs_idempotency_of_channel_openings(
    token_network_model: TokenNetwork,
    addresses: List[Address],
    pathfinding_service_mocked_listeners: PathfindingService,
):
    registry_listener = pathfinding_service_mocked_listeners.token_network_registry_listener
    # assert registry_listener

    token_network_address = token_network_model.address

    # this is a new pathfinding service, there should be no token networks registered
    assert len(pathfinding_service_mocked_listeners.token_networks.keys()) == 0

    # emit a TokenNetworkCreated event
    registry_listener.emit_event(dict(
        event='TokenNetworkCreated',
        blockNumber=12,
        args=dict(
            token_network_address=token_network_address,
            token_address=token_network_model.token_address,
        ),
    ))

    # now there should be a token network registered
    assert token_network_address in pathfinding_service_mocked_listeners.token_networks
    token_network = pathfinding_service_mocked_listeners.token_networks[token_network_address]

    assert len(pathfinding_service_mocked_listeners.token_network_listeners) == 1
    network_listener = pathfinding_service_mocked_listeners.token_network_listeners[0]

    # create same channel 5 times
    for _ in range(5):
        network_listener.emit_event(dict(
            address=token_network_address,
            event='ChannelOpened',
            args=dict(
                channel_identifier=decode_hex('0x%064x' % 1),
                participant1=addresses[0],
                participant2=addresses[1],
                settle_timeout=15,
            ),
        ))

    # there should only be one channel
    assert len(token_network.channel_id_to_addresses.keys()) == 1

    # now close the channel
    network_listener.emit_event(dict(
        address=token_network_address,
        event='ChannelClosed',
        args=dict(
            channel_identifier=decode_hex('0x%064x' % 1),
            closing_participant=addresses[0],
        ),
    ))

    # there should be no channels
    assert len(token_network.channel_id_to_addresses.keys()) == 0


def test_pfs_multiple_channels_for_two_participants_opened(
    token_network_model: TokenNetwork,
    addresses: List[Address],
    pathfinding_service_mocked_listeners: PathfindingService,
):
    registry_listener = pathfinding_service_mocked_listeners.token_network_registry_listener
    # assert registry_listener

    token_network_address = token_network_model.address

    # this is a new pathfinding service, there should be no token networks registered
    assert len(pathfinding_service_mocked_listeners.token_networks.keys()) == 0

    # emit a TokenNetworkCreated event
    registry_listener.emit_event(dict(
        event='TokenNetworkCreated',
        blockNumber=12,
        args=dict(
            token_network_address=token_network_address,
            token_address=token_network_model.token_address,
        ),
    ))

    # now there should be a token network registered
    assert token_network_address in pathfinding_service_mocked_listeners.token_networks
    token_network = pathfinding_service_mocked_listeners.token_networks[token_network_address]

    assert len(pathfinding_service_mocked_listeners.token_network_listeners) == 1
    network_listener = pathfinding_service_mocked_listeners.token_network_listeners[0]

    # create a channel
    network_listener.emit_event(dict(
        address=token_network_address,
        event='ChannelOpened',
        args=dict(
            channel_identifier=decode_hex('0x%064x' % 1),
            participant1=addresses[0],
            participant2=addresses[1],
            settle_timeout=15,
        ),
    ))

    # create a channel
    network_listener.emit_event(dict(
        address=token_network_address,
        event='ChannelOpened',
        args=dict(
            channel_identifier=decode_hex('0x%064x' % 2),
            participant1=addresses[1],
            participant2=addresses[0],
            settle_timeout=15,
        ),
    ))

    # now there should be two channels
    assert len(token_network.channel_id_to_addresses.keys()) == 2

    # now close one channel
    network_listener.emit_event(dict(
        address=token_network_address,
        event='ChannelClosed',
        args=dict(
            channel_identifier=decode_hex('0x%064x' % 1),
            closing_participant=addresses[0],
        ),
    ))

    # there should be one channel left
    assert len(token_network.channel_id_to_addresses.keys()) == 1
