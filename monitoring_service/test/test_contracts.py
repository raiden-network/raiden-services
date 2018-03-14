import pytest
import gevent
from eth_utils import is_same_address
from eth_tester.exceptions import TransactionFailed
from monitoring_service.utils import make_filter
from monitoring_service.contract_manager import CONTRACT_MANAGER


def test_deploy(generate_raiden_client, ethereum_tester):
    c1, c2 = generate_raiden_client(), generate_raiden_client()
    c3 = generate_raiden_client()
    web3 = c1.web3

    # make filter for ChannelClosed event
    # get event ABI
    abi = CONTRACT_MANAGER.get_event_abi('NettingChannelContract', 'ChannelClosed')
    event_filter = make_filter(web3, abi[0])

    channel_addr = c1.open_channel(c2.address)
    # initialy it should be empty
    transfer_events = event_filter.get_new_entries()
    assert transfer_events == []
    # now close a channel and check if we got the entry
    c1.close_channel(c2.address)
    transfer_events = event_filter.get_new_entries()
    assert transfer_events != []
    assert is_same_address(transfer_events[0]['args']['closing_address'], c1.address)
    assert is_same_address(transfer_events[0]['address'], channel_addr)
    # no new entries
    transfer_events = event_filter.get_new_entries()
    assert transfer_events == []
    # open/close another channel, get new entry
    channel_addr = c3.open_channel(c1.address)
    c3.close_channel(c1.address)
    transfer_events = event_filter.get_new_entries()
    assert transfer_events != []
    assert is_same_address(transfer_events[0]['args']['closing_address'], c3.address)
    assert is_same_address(transfer_events[0]['address'], channel_addr)

    with pytest.raises(TransactionFailed):
        c1.settle_channel(c2.address)
    ethereum_tester.mine_blocks(num_blocks=10)
    with pytest.raises(TransactionFailed):
        c1.settle_channel(c2.address)

    ethereum_tester.mine_blocks(num_blocks=10)
    c1.settle_channel(c2.address)


def test_first_event(generate_raiden_client, web3):
    c1, c2 = generate_raiden_client(), generate_raiden_client()
    channel_addr = c1.open_channel(c2.address)
    c1.close_channel(c2.address)
    gevent.sleep(0)
    abi = CONTRACT_MANAGER.get_event_abi('NettingChannelContract', 'ChannelClosed')
    event_filter = make_filter(web3, abi[0], fromBlock=0)
    transfer_events = event_filter.get_new_entries()
    assert len(transfer_events) > 0
    assert [x for x in transfer_events if is_same_address(x['address'], channel_addr)]


def meta_update_transfer(generate_raiden_client, web3, updates=list()):
    assert len(updates) >= 2
    c1, c2 = generate_raiden_client(), generate_raiden_client()
    channel_addr = c1.open_channel(c2.address)
    c1.deposit_to_channel(c2.address, 100)
    assert is_same_address(c2.open_channel(c1.address), channel_addr)

    # c1 closes the channel
    balance_proof_c1 = c2.get_balance_proof(c1.address, updates[0])
    c1.close_channel(c2.address, balance_proof_c1)

    # c2 calls update transfer
    for amount in updates[1:]:
        balance_proof_c2 = c1.get_balance_proof(
            c2.address,
            amount
        )

        c2.update_transfer(c1.address, balance_proof_c2)


def test_update_transfer(generate_raiden_client, web3):
    """Test (valid) update channel"""
    meta_update_transfer(generate_raiden_client, web3, [0, 1])
    meta_update_transfer(generate_raiden_client, web3, [1, 0])
