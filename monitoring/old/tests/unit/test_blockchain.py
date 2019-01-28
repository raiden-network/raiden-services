import gevent

from old.utils.blockchain_listener import create_channel_event_topics
from raiden_contracts.constants import ChannelEvent
from raiden_contracts.contract_manager import ContractManager
from raiden_libs.utils import make_filter


def test_blockchain(generate_raiden_client, blockchain, wait_for_blocks):
    trigger_count = 0

    def trigger_closed(ev, tx):
        nonlocal trigger_count
        if ev['event'] == ChannelEvent.CLOSED:
            trigger_count += 1

    def trigger_settled(ev, tx):
        nonlocal trigger_count
        if ev['event'] == ChannelEvent.SETTLED:
            trigger_count += 1

    blockchain.add_confirmed_listener(
        create_channel_event_topics(),
        trigger_closed,
    )
    blockchain.add_confirmed_listener(
        create_channel_event_topics(),
        trigger_settled,
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

    assert trigger_count == 1

    wait_for_blocks(30)
    c1.settle_channel(
        c2.address,
        (0, bp.transferred_amount),
        (0, bp.locked_amount),
        ('0x%064x' % 0, bp.locksroot),
    )
    wait_for_blocks(4)
    blockchain._update()

    assert trigger_count == 2


def test_filter(
        generate_raiden_client,
        web3,
        contracts_manager: ContractManager,
):
    """test if filter returns past events"""
    c1 = generate_raiden_client()
    c2 = generate_raiden_client()
    c3 = generate_raiden_client()
    channel_id = c1.open_channel(c2.address)
    bp = c2.get_balance_proof(c1.address, transferred_amount=1, nonce=1)

    c1.close_channel(c2.address, bp)
    gevent.sleep(0)

    abi = contracts_manager.get_event_abi('TokenNetwork', 'ChannelClosed')
    assert abi is not None
    f = make_filter(web3, abi, fromBlock=0)
    entries = f.get_new_entries()
    assert len([
        x for x in entries
        if (
            x['args']['channel_identifier'] == channel_id and
            x['address'] == c1.contract.address
        )
    ]) == 1

    channel_id = c1.open_channel(c3.address)
    bp = c3.get_balance_proof(c1.address, transferred_amount=1, nonce=1)
    c1.close_channel(c3.address, bp)
    entries = f.get_new_entries()
    assert len([
        x for x in entries
        if (
            x['args']['channel_identifier'] == channel_id and
            x['address'] == c1.contract.address
        )
    ]) == 1
    assert len(f.get_all_entries()) > 0
