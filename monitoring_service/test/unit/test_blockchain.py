import gevent
from monitoring_service.constants import (
    EVENT_CHANNEL_CLOSE,
    EVENT_CHANNEL_SETTLED,
    EVENT_TRANSFER_UPDATED
)
from raiden_contracts.contract_manager import CONTRACT_MANAGER
from raiden_libs.utils import make_filter


# test if ChannelClosed event triggers an callback of the blockchain wrapper
class Trigger:
    def __init__(self):
        self.trigger_count = 0

    def trigger(self, *args):
        self.trigger_count += 1


def test_blockchain(generate_raiden_client, blockchain, wait_for_blocks):

    t = Trigger()

    blockchain.add_confirmed_listener(
        EVENT_CHANNEL_CLOSE,
        lambda ev, tx: t.trigger()
    )
    blockchain.add_confirmed_listener(
        EVENT_CHANNEL_SETTLED,
        lambda ev, tx: t.trigger()
    )
    blockchain.add_confirmed_listener(
        EVENT_TRANSFER_UPDATED,
        lambda ev, tx: t.trigger()
    )
    blockchain.poll_interval = 0
    blockchain._update()

    c1 = generate_raiden_client()
    c2 = generate_raiden_client()
    c1.open_channel(c2.address)
    c2.open_channel(c1.address)
    c2.deposit_to_channel(c1.address, 10)
    c1.deposit_to_channel(c2.address, 10)
    bp = c2.get_balance_proof(c1.address, transferred_amount=1, nonce=1)
    c1.close_channel(c2.address, bp)
    wait_for_blocks(5)
    blockchain._update()

    assert t.trigger_count == 1

    wait_for_blocks(30)
    c1.settle_channel(c2.address)
    wait_for_blocks(4)
    blockchain._update()

    assert t.trigger_count == 2


def test_filter(generate_raiden_client, web3):
    """test if filter returns past events"""
    c1 = generate_raiden_client()
    c2 = generate_raiden_client()
    c3 = generate_raiden_client()
    channel_id = c1.open_channel(c2.address)
    bp = c2.get_balance_proof(c1.address, transferred_amount=1, nonce=1)

    c1.close_channel(c2.address, bp)
    gevent.sleep(0)

    abi = CONTRACT_MANAGER.get_event_abi('TokenNetwork', 'ChannelClosed')
    assert abi is not None
    f = make_filter(web3, abi, fromBlock=0)
    entries = f.get_new_entries()
    assert len([
        x for x in entries
        if (x['args']['channel_identifier'] == channel_id) and
        (x['address'] == c1.contract.address)
    ]) == 1

    channel_id = c1.open_channel(c3.address)
    bp = c3.get_balance_proof(c1.address, transferred_amount=1, nonce=1)
    c1.close_channel(c3.address, bp)
    entries = f.get_new_entries()
    assert len([
        x for x in entries
        if (x['args']['channel_identifier'] == channel_id) and
        (x['address'] == c1.contract.address)
    ]) == 1
    assert len(f.get_all_entries()) > 0
