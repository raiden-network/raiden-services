from monitoring_service.tasks import StoreMonitorRequest
import copy


def test_validate_bp(web3, generate_raiden_client, get_random_address, state_db_sqlite):
    c1, c2 = generate_raiden_client(), generate_raiden_client()
    c1.open_channel(c2.address)
    state_db_sqlite.setup_db(1, get_random_address(), get_random_address())

    balance_proof = c1.get_balance_proof(c2.address, transferred_amount=1, nonce=1)
    monitor_request = c1.get_monitor_request(c2.address, balance_proof, 1, get_random_address())

    # test happy case: balance proof is valid
    task = StoreMonitorRequest(web3, state_db_sqlite, monitor_request)
    assert task._run() is True

    # balance proof with an invalid contract address
    mr_copy = copy.deepcopy(monitor_request)
    mr_copy.token_network_address = get_random_address()
    task = StoreMonitorRequest(web3, state_db_sqlite, mr_copy)
    task._run()
    assert task._run() is False

    # balance proof with an invalid sender
    mr_copy = copy.deepcopy(monitor_request)
    mr_copy.reward_sender_address = get_random_address()
    task = StoreMonitorRequest(web3, state_db_sqlite, mr_copy)
    task._run()
    assert task._run() is False
