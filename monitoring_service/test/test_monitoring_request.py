

def test_monitoring_request(
    web3,
    generate_raiden_clients,
    monitoring_service,
    wait_for_blocks,
):
    reward_amount = 1
    c1, c2 = generate_raiden_clients(2)
    c1.open_channel(c2.address)
    balance_proof = c1.get_balance_proof(
        c2.address,
        nonce=1,
        transferred_amount=1,
        locksroot='0x%064x' % 0,
        additional_hash='0x%064x' % 0,
        locked_amount=0,
    )
    monitor_request = c1.get_monitor_request(
        c2.address,
        balance_proof,
        reward_amount,
        monitoring_service.address,
    )

    wait_for_blocks(1)  # wait for the ChannelOpened event to be confirmed
    monitoring_service.transport.receive_fake_data(monitor_request.serialize_full())
    monitoring_service.wait_tasks()
