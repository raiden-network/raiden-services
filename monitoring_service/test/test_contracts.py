import pytest
import gevent
from eth_utils import is_same_address
from eth_tester.exceptions import TransactionFailed
from monitoring_service.utils import make_filter
from raiden_contracts.contract_manager import CONTRACT_MANAGER


def test_deploy(generate_raiden_client, ethereum_tester):
    c1, c2 = generate_raiden_client(), generate_raiden_client()
    c3 = generate_raiden_client()
    web3 = c1.web3

    # make filter for ChannelClosed event
    # get event ABI
    abi = CONTRACT_MANAGER.get_event_abi('TokenNetwork', 'ChannelClosed')
    event_filter = make_filter(web3, abi)
    # deposit some funds to the channel

    channel_id = c1.open_channel(c2.address)
    c1.deposit_to_channel(c2.address, 100)
    channel_id_c2 = c2.open_channel(c1.address)
    c2.deposit_to_channel(c1.address, 100)
    assert channel_id == channel_id_c2
    # initialy it should be empty
    transfer_events = event_filter.get_new_entries()
    assert transfer_events == []
    # now close a channel and check if we got the entry
    c1_balance_proof = c2.get_balance_proof(c1.address, transferred_amount=10, nonce=5)
    c1.close_channel(c2.address, c1_balance_proof)
    transfer_events = event_filter.get_new_entries()
    assert transfer_events != []
    assert is_same_address(transfer_events[0]['args']['closing_participant'], c1.address)
    assert transfer_events[0]['args']['channel_identifier'] == channel_id
    # no new entries
    transfer_events = event_filter.get_new_entries()
    assert transfer_events == []
    # open/close another channel, get new entry
    channel_id = c3.open_channel(c1.address)
    c1.open_channel(c3.address)
    c1_balance_proof = c1.get_balance_proof(c3.address, transferred_amount=10, nonce=3)
    c3.close_channel(c1.address, c1_balance_proof)
    transfer_events = [
        event
        for event in event_filter.get_new_entries()
        if is_same_address(event['args']['closing_participant'], c3.address)
    ]
    assert transfer_events != []
    assert is_same_address(transfer_events[0]['args']['closing_participant'], c3.address)
    assert transfer_events[0]['args']['channel_identifier'] == channel_id

    with pytest.raises(TransactionFailed):
        c1.settle_channel(c2.address)
    ethereum_tester.mine_blocks(num_blocks=10)
    with pytest.raises(TransactionFailed):
        c1.settle_channel(c2.address)

    ethereum_tester.mine_blocks(num_blocks=10)
    c1.settle_channel(c2.address)


def test_first_event(generate_raiden_client, web3):
    c1, c2 = generate_raiden_client(), generate_raiden_client()
    channel_id = c1.open_channel(c2.address)
    channel_id_c2 = c2.open_channel(c1.address)
    assert channel_id == channel_id_c2
    c2_balance_proof = c2.get_balance_proof(c1.address, transferred_amount=10, nonce=1)
    c1.close_channel(c2.address, c2_balance_proof)
    gevent.sleep(0)
    abi = CONTRACT_MANAGER.get_event_abi('TokenNetwork', 'ChannelClosed')
    event_filter = make_filter(web3, abi, fromBlock=0)
    transfer_events = event_filter.get_new_entries()
    assert len(transfer_events) > 0
    assert [
        x for x in transfer_events
        if is_same_address(x['args']['closing_participant'], c1.address)
    ]


def meta_update_transfer(generate_raiden_client, web3, updates=list()):
    assert len(updates) >= 2
    c1, c2 = generate_raiden_client(), generate_raiden_client()
    channel_id = c1.open_channel(c2.address)
    c1.deposit_to_channel(c2.address, 100)
    channel_id_c2 = c2.open_channel(c1.address)
    c2.deposit_to_channel(c1.address, 100)
    assert channel_id == channel_id_c2

    # c1 closes the channel
    nonce = 1
    balance_proof_c1 = c2.get_balance_proof(c1.address, transferred_amount=updates[0], nonce=nonce)
    c1.close_channel(c2.address, balance_proof_c1)

    # c2 calls update transfer
    for amount in updates[1:]:
        nonce += 1
        balance_proof_c2 = c1.get_balance_proof(
            c2.address,
            transferred_amount=amount,
            nonce=nonce
        )

        c2.update_transfer(c1.address, balance_proof_c2)


def test_update_transfer(generate_raiden_client, web3):
    """Test (valid) update channel"""
    meta_update_transfer(generate_raiden_client, web3, [0, 1])
    meta_update_transfer(generate_raiden_client, web3, [1, 0])
