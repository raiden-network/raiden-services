import gevent
from eth_utils import is_same_address
from monitoring_service.constants import (
    EVENT_CHANNEL_CLOSE,
    EVENT_CHANNEL_SETTLED,
    EVENT_TRANSFER_UPDATED
)
from monitoring_service.contract_manager import CONTRACT_MANAGER
from monitoring_service.utils import make_filter


# test if ChannelClosed event triggers an callback of the blockchain wrapper
class Trigger:
    def __init__(self):
        self.trigger_count = 0

    def trigger(self, *args):
        self.trigger_count += 1


def test_blockchain(generate_raiden_client, blockchain, wait_for_blocks):

    t = Trigger()

    blockchain.register_handler(
        EVENT_CHANNEL_CLOSE,
        lambda ev, tx: t.trigger()
    )
    blockchain.register_handler(
        EVENT_CHANNEL_SETTLED,
        lambda ev, tx: t.trigger()
    )
    blockchain.register_handler(
        EVENT_TRANSFER_UPDATED,
        lambda ev, tx: t.trigger()
    )
    blockchain.event_filters = blockchain.make_filters()
    blockchain.poll_interval = 0

    c1 = generate_raiden_client()
    c2 = generate_raiden_client()
    c1.open_channel(c2.address)
    c1.close_channel(c2.address)
    blockchain.poll_blockchain()

    assert t.trigger_count == 1

    wait_for_blocks(30)
    c1.settle_channel(c2.address)
    blockchain.poll_blockchain()

    assert t.trigger_count == 2


def test_filter(generate_raiden_client, web3):
    """test if filter returns past events"""
    c1 = generate_raiden_client()
    c2 = generate_raiden_client()
    c3 = generate_raiden_client()
    channel_addr = c1.open_channel(c2.address)
    c1.close_channel(c2.address)
    gevent.sleep(0)

    abi = CONTRACT_MANAGER.get_event_abi('NettingChannelContract', 'ChannelClosed')
    assert abi is not None
    f = make_filter(web3, abi[0], fromBlock=0)
    entries = f.get_new_entries()
    assert len([
        x for x in entries
        if is_same_address(x['address'], channel_addr)
    ]) == 1
    c1.open_channel(c3.address)
    c1.close_channel(c3.address)
    assert len(f.get_new_entries()) == 1
    assert len(f.get_all_entries()) > 0
