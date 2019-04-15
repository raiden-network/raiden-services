from raiden.utils.typing import BlockNumber, ChannelID
from raiden_libs.events import ReceiveChannelOpenedEvent, ReceiveTokenNetworkCreatedEvent
from raiden_libs.types import Address, TokenNetworkAddress


def test_save_and_load_token_networks(pathfinding_service_mock):
    pfs = pathfinding_service_mock
    pfs.token_networks = {}  # the mock does not fit this case exactly

    token_address = Address('0x' + '1' * 40)
    token_network_address = TokenNetworkAddress('0x' + '2' * 40)
    channel_id = ChannelID(1)
    p1 = Address('0x' + '3' * 40)
    p2 = Address('0x' + '4' * 40)
    events = [
        ReceiveTokenNetworkCreatedEvent(
            token_address=token_address,
            token_network_address=token_network_address,
            block_number=BlockNumber(1),
        ),
        ReceiveChannelOpenedEvent(
            token_network_address=token_network_address,
            channel_identifier=channel_id,
            participant1=p1,
            participant2=p2,
            settle_timeout=1000,
            block_number=BlockNumber(2),
        ),
    ]
    for event in events:
        pfs.handle_event(event)
    assert len(pfs.token_networks) == 1

    loaded_networks = pfs._load_token_networks()
    assert len(loaded_networks) == 1

    orig = list(pfs.token_networks.values())[0]
    loaded = list(loaded_networks.values())[0]
    assert loaded.address == orig.address
    assert loaded.channel_id_to_addresses == orig.channel_id_to_addresses
    assert loaded.G.nodes == orig.G.nodes
