def test_state_db_sqlite(state_db_sqlite, get_random_monitor_request, get_random_address):
    state_db_sqlite.setup_db(1, get_random_address(), get_random_address())
    request = get_random_monitor_request()
    request_json = request.serialize_data()
    state_db_sqlite.store_monitor_request(request_json)
    ret = state_db_sqlite.monitor_requests
    fields_to_check = list(request_json.keys())
    fields_to_check.remove('chain_id')
    fields_to_check.remove('monitor_address')
    for x in fields_to_check:
        assert request_json[x] == ret[request_json['channel_identifier']][x]
