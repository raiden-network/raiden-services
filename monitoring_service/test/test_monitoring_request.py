import gevent


def test_monitoring_request(
    generate_raiden_clients,
    monitoring_service,
    wait_for_blocks
):
    reward_amount = 1
    c1, c2 = generate_raiden_clients(2)
    c1.open_channel(c2.address)
    balance_proof = c1.get_balance_proof(c2.address, nonce=1, transferred_amount=1)
    monitor_request = c1.get_monitor_request(
        c2.address,
        balance_proof,
        reward_amount,
        monitoring_service.address
    )

    monitoring_service.start()
    gevent.sleep(0)
    monitoring_service.transport.send_message(monitor_request)
    monitoring_service.wait_tasks()
