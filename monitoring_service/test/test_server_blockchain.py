import gevent
from eth_utils import is_same_address


def test_close_event(
    generate_raiden_clients,
    monitoring_service,
    wait_for_blocks
):
    """Test opening, closing and settling the channel"""
    monitoring_service.start()
    gevent.sleep(1)
    c1, c2 = generate_raiden_clients(2)
    # open a channel
    channel_address = c1.open_channel(c2.address)
    msg = c1.get_balance_proof(c2.address, 10)

    monitoring_service.transport.send_message(msg)

    # close it
    c1.close_channel(c2.address)
    gevent.sleep(1)
    wait_for_blocks(30)
    # settle
    c1.settle_channel(c2.address)
    gevent.sleep(1)
    # test if the channel is no longer in MS' channel list
    assert channel_address not in monitoring_service.balance_proofs


def test_transfer_update_event(
    generate_raiden_clients,
    monitoring_service,
    wait_for_blocks
):
    """Test transfer update event"""
    monitoring_service.start()
    gevent.sleep(1)
    c1, c2 = generate_raiden_clients(2)
    channel_address = c1.open_channel(c2.address)
    channel_address_2 = c2.open_channel(c1.address)
    assert is_same_address(channel_address, channel_address_2)

    # generate BP for client 1 and register it
    msg = c1.get_balance_proof(c2.address, 10)

    monitoring_service.transport.send_message(msg)

    # close the channel without a balance proof
    c1.close_channel(c2.address)

    # server should respond by calling updateTransfer
    gevent.sleep(1)

    wait_for_blocks(30)
    # settle
    c1.settle_channel(c2.address)
    gevent.sleep(1)
    # test if the channel is no longer in MS' channel list
    assert channel_address not in monitoring_service.balance_proofs
