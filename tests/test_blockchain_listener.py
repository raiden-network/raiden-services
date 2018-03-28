# -*- coding: utf-8 -*-
import gevent


def test_blockchain_listener(
    generate_raiden_clients,
    blockchain_listener,
    ethereum_tester,
):
    """ Test confirmed and unconfirmed events. """
    events_confirmed = []
    events_unconfirmed = []
    blockchain_listener.add_confirmed_listener(
        'ChannelOpened',
        lambda e: events_confirmed.append(e)
    )
    blockchain_listener.add_unconfirmed_listener(
        'ChannelOpened',
        lambda e: events_unconfirmed.append(e)
    )

    # start the blockchain listener
    blockchain_listener.start()

    c1, c2 = generate_raiden_clients(2)
    c1.open_channel(c2.address)

    ethereum_tester.mine_block()
    gevent.sleep()

    # the unconfirmed event should be received now
    assert len(events_unconfirmed) == 1

    # mine 3 more blocks, that should make the event confirmed
    ethereum_tester.mine_blocks(3)
    gevent.sleep()

    assert len(events_confirmed) == 1

    blockchain_listener.stop()
