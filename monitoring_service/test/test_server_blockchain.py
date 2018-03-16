import gevent


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
    channel_id = c1.open_channel(c2.address)
    c2.open_channel(c1.address)
    c2.deposit_to_channel(c1.address, 100)
    msg = c1.get_balance_proof(c2.address, transferred_amount=10, nonce=1)

    monitoring_service.transport.send_message(msg)

    # close it
    c2.close_channel(c1.address, msg)
    gevent.sleep(1)
    wait_for_blocks(30)
    # settle
    c2.settle_channel(c1.address)
    gevent.sleep(1)
    # test if the channel is no longer in MS' channel list
    assert channel_id not in monitoring_service.balance_proofs


def test_transfer_update_event(
    generate_raiden_clients,
    monitoring_service,
    wait_for_blocks
):
    """Test transfer update event"""
    monitoring_service.start()
    gevent.sleep(1)
    c1, c2 = generate_raiden_clients(2)
    channel_id = c1.open_channel(c2.address)
    channel_id_2 = c2.open_channel(c1.address)
    c1.deposit_to_channel(c2.address, 100)
    c2.deposit_to_channel(c1.address, 100)
    assert channel_id == channel_id_2

    # generate BP for client 1 and register it
    msg = c1.get_balance_proof(c2.address, transferred_amount=10, nonce=1)
    msg_2 = c2.get_balance_proof(c1.address, transferred_amount=12, nonce=1)

    monitoring_service.transport.send_message(msg_2)

    # close the channel with an older BP
    c2.close_channel(c1.address, msg)

    # server should respond by calling updateTransfer
    gevent.sleep(1)

    wait_for_blocks(30)
    # settle
    c1.settle_channel(c2.address)
    gevent.sleep(1)
    # test if the channel is no longer in MS' channel list
    assert channel_id not in monitoring_service.balance_proofs
