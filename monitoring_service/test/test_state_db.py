def test_state_db_sqlite(state_db_sqlite, get_random_monitor_request, get_random_address):
    request = get_random_monitor_request()
    state_db_sqlite.store_monitor_request(request)
    ret = list(state_db_sqlite.get_monitor_requests().values())
    assert len(ret) == 1
    # Don't really check monitor_address, since it's not used. Remove after solving
    # https://github.com/raiden-network/raiden-monitoring-service/issues/42
    ret[0].monitor_address = request.monitor_address
    assert ret[0].serialize_data() == request.serialize_data()


def test_requests_by_both_participants(
        get_monitor_request_for_same_channel,
        state_db_sqlite,
        get_random_address,
):
    """ Make sure that we store MRs for both participants in the channel

    Regression test for https://github.com/raiden-network/raiden-monitoring-service/issues/34.
    """
    mr1 = get_monitor_request_for_same_channel(user=0)
    mr2 = get_monitor_request_for_same_channel(user=1)
    for mr in (mr1, mr2):
        state_db_sqlite.store_monitor_request(mr)

    all_monitor_requests = state_db_sqlite.get_monitor_requests()
    assert len(all_monitor_requests) == 2
