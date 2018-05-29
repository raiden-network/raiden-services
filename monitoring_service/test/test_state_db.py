def check_monitor_request(data_sqlite, request_json):
    # check monitor request fields
    fields_to_check = list(request_json.keys())
    fields_to_check.remove('balance_proof')
    fields_to_check.remove('monitor_address')
    to_check = data_sqlite[request_json['balance_proof']['channel_identifier']]
    for x in fields_to_check:
        assert request_json[x] == to_check[x]

    # check balance proof fields
    balance_proof = request_json['balance_proof']
    fields_to_check = list(balance_proof.keys())
    fields_to_check.remove('chain_id')
    fields_to_check.remove('signature')
    for x in fields_to_check:
        assert balance_proof[x] == to_check[x]
    assert balance_proof['signature'] == to_check['closing_signature']


def test_state_db_sqlite(state_db_sqlite, get_random_monitor_request, get_random_address):
    state_db_sqlite.setup_db(1, get_random_address(), get_random_address())
    request = get_random_monitor_request()
    request_json = request.serialize_data()
    state_db_sqlite.store_monitor_request(request_json)
    ret = state_db_sqlite.monitor_requests
    check_monitor_request(ret, request_json)
