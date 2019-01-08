import copy

from monitoring_service.tasks import StoreMonitorRequest


def test_validate_bp(web3, generate_raiden_client, get_random_address, state_db_sqlite):
    c1, c2 = generate_raiden_client(), generate_raiden_client()
    c1.open_channel(c2.address)

    balance_proof = c1.get_balance_proof(
        c2.address,
        nonce=1,
        balance_hash='0x%064x' % 0,
    )
    monitor_request = c1.get_monitor_request(c2.address, balance_proof, 1, get_random_address())

    # test happy case: balance proof is valid
    task = StoreMonitorRequest(web3, state_db_sqlite, monitor_request)
    assert task._run() is True

    # balance proof with an invalid contract address
    mr_copy = copy.deepcopy(monitor_request)
    mr_copy.balance_proof.token_network_address = get_random_address()
    task = StoreMonitorRequest(web3, state_db_sqlite, mr_copy)
    task._run()
    assert task._run() is False
