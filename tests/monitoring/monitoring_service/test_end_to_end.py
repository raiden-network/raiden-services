import gevent

from monitoring_service.service import MonitoringService


def test_e2e(
    web3,
    generate_raiden_clients,
    monitoring_service_contract,
    user_deposit_contract,
    wait_for_blocks,
    custom_token,
    raiden_service_bundle,
    monitoring_service: MonitoringService,
):
    """Test complete message lifecycle
        1) client opens channel & submits monitoring request
        2) other client closes channel
        3) MS registers channelClose event
        4) MS calls monitoring contract update
        5) wait for channel settle
        6) MS claims the reward
    """
    user_deposit_contract.functions.init(monitoring_service_contract.address).transact()
    # user_deposit_contract.functions.balances(
    #     monitoring_service.address,
    # ).call()
    c1, c2 = generate_raiden_clients(2)

    # add deposit for c1
    # TODO: this should be done via RSB at some point
    node_deposit = 10
    custom_token.functions.approve(
        user_deposit_contract.address,
        node_deposit,
    ).transact({'from': c1.address})
    user_deposit_contract.functions.deposit(
        c1.address, node_deposit,
    ).transact({'from': c1.address})

    # each client does a transfer
    c1.open_channel(c2.address)
    # balance_proof_c1 = c1.get_balance_proof(
    #     c2.address,
    #     nonce=1,
    #     transferred_amount=5,
    #     locked_amount=0,
    #     locksroot='0x%064x' % 0,
    #     additional_hash='0x%064x' % 0,
    # )
    # balance_proof_c2 = c2.get_balance_proof(
    #     c1.address,
    #     nonce=2,
    #     transferred_amount=6,
    #     locked_amount=0,
    #     locksroot='0x%064x' % 0,
    #     additional_hash='0x%064x' % 0,
    # )

    gevent.spawn(monitoring_service.start, gevent.sleep)

    # need to wait here till the MS has some time to react
    gevent.sleep()

    assert monitoring_service.ms_state.blockchain_state.token_network_addresses
    # c1 asks MS to monitor the channel
    # reward_amount = 1
    # monitor_request = c1.get_monitor_request(
    #     c2.address,
    #     balance_proof_c2,
    #     reward_amount,
    #     monitoring_service.address,
    # )
    # # wait for channel open event to be processed by the MS
    # wait_for_blocks(1)
    # gevent.sleep(TEST_POLL_INTERVAL)

    # request_collector.transport.receive_fake_data(monitor_request.serialize_full())
    # gevent.sleep(1)
    # assert (channel_id, c1.address) in monitoring_service.monitor_requests
    #
    # c2.close_channel(c1.address, balance_proof_c1)
    # # Wait one block until the ChannelClosed event is confirmed and handled
    # # by the MS
    # wait_for_blocks(1)
    # # Now give the monitoring service a chance to submit the missing BP
    # # (why does it take longer than TEST_POLL_INTERVAL in some cases?)
    # gevent.sleep(0.1)
    # assert [e.event for e in blockchain_validator.events] == ['NewBalanceProofReceived']
    #
    # # wait for settle timeout
    # wait_for_blocks(15)
    # c2.settle_channel(
    #     c1.address,
    #     (balance_proof_c2.transferred_amount, balance_proof_c1.transferred_amount),
    #     (balance_proof_c2.locked_amount, balance_proof_c1.locked_amount),
    #     (balance_proof_c1.locksroot, balance_proof_c1.locksroot),
    # )
    # # Wait until the ChannelSettled is confirmed
    # wait_for_blocks(1)
    # # Let the MS claim its reward (for some reason this takes longer than TEST_POLL_INTERVAL)
    # gevent.sleep(0.1)
    # assert [e.event for e in blockchain_validator.events] == [
    #     'NewBalanceProofReceived', 'RewardClaimed',
    # ]
    #
    # final_balance = user_deposit_contract.functions.balances(
    #     monitoring_service.address,
    # ).call()
    # assert final_balance == (initial_balance + reward_amount)
