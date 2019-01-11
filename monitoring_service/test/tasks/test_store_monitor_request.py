import gevent

from request_collector.store_monitor_request import StoreMonitorRequest


def test_request_validation(
        web3,
        get_monitor_request_for_same_channel,
        state_db_sqlite,
        get_random_address,
):
    def store_successful(mr):
        task = StoreMonitorRequest(state_db_sqlite, mr)
        task.run()
        gevent.joinall([task])
        return len(state_db_sqlite.get_monitor_requests()) == 1

    # invalid signatures
    invalid_sig = '0x' + '0' * 130
    mr = get_monitor_request_for_same_channel(user=0)
    mr.reward_proof_signature = invalid_sig
    assert not store_successful(mr)

    mr = get_monitor_request_for_same_channel(user=0)
    mr.balance_proof.signature = invalid_sig
    assert not store_successful(mr)

    mr = get_monitor_request_for_same_channel(user=0)
    mr.non_closing_signature = invalid_sig
    assert not store_successful(mr)

    # signatures by wrong party
    mr = get_monitor_request_for_same_channel(user=0, bad_key_for_bp=True)
    assert not store_successful(mr)

    mr = get_monitor_request_for_same_channel(user=0, bad_key_for_non_closing=True)
    assert not store_successful(mr)

    # must fail because no reward is deposited
    # TODO: enable once we check deposits
    # mr = get_monitor_request_for_same_channel(user=0, reward_amount=1)
    # task = StoreMonitorRequest(web3, state_db_sqlite, mr)
    # task.run()
    # gevent.joinall([task])
    # assert len(state_db_sqlite.get_monitor_requests()) == 0

    # everything ok
    mr = get_monitor_request_for_same_channel(user=0)
    assert store_successful(mr)


def test_save_mr_from_transport(
    request_collector,
    get_monitor_request_for_same_channel,
    state_db_sqlite,
):
    """Does the request collector save submitted MRs?"""
    monitor_request = get_monitor_request_for_same_channel(user=0)
    transport = request_collector.transport
    transport.receive_fake_data(monitor_request.serialize_full())
    request_collector.wait_tasks()
    len(request_collector.monitor_requests) == 1
