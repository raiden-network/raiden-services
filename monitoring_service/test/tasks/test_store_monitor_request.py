import gevent

from monitoring_service.tasks.store_monitor_request import StoreMonitorRequest


def test_request_validation(
        web3,
        get_monitor_request_for_same_channel,
        state_db_sqlite,
        get_random_address,
):
    def store_successful(mr):
        task = StoreMonitorRequest(web3, state_db_sqlite, mr)
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
    # TODO: enable once we check participant addresses
    # mr = get_monitor_request_for_same_channel(user=0, bad_key_for_bp=True)
    # assert not store_successful(mr)

    # mr = get_monitor_request_for_same_channel(user=0, bad_key_for_non_closing=True)
    # assert not store_successful(mr)

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
