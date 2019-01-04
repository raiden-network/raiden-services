from eth_utils import encode_hex

import pytest
from raiden_libs.messages import BalanceProof, MonitorRequest
from raiden_libs.utils import sha3
from raiden_libs.utils.signing import eth_sign


def check_monitor_request(data_sqlite, request_json):
    # check monitor request fields
    fields_to_check = list(request_json.keys())
    fields_to_check.remove('balance_proof')
    fields_to_check.remove('monitor_address')
    to_check = list(data_sqlite.values())[0]
    for x in fields_to_check:
        assert request_json[x] == to_check[x]

    # check balance proof fields
    balance_proof = request_json['balance_proof']
    fields_to_check = list(balance_proof.keys())
    fields_to_check.remove('chain_id')
    fields_to_check.remove('signature')
    for x in fields_to_check:
        assert balance_proof[x] == to_check[x], f'Field "{x}" does not match'
    assert balance_proof['signature'] == to_check['closing_signature']


def test_state_db_sqlite(state_db_sqlite, get_random_monitor_request, get_random_address):
    state_db_sqlite.setup_db(1, get_random_address(), get_random_address())
    request = get_random_monitor_request()
    state_db_sqlite.store_monitor_request(request)
    ret = state_db_sqlite.monitor_requests
    check_monitor_request(ret, request.serialize_data())


def test_requests_by_both_participants(
        get_monitor_request_for_same_channel,
        state_db_sqlite,
        get_random_address
):
    """ Make sure that we store MRs for both participants in the channel

    Regression test for https://github.com/raiden-network/raiden-monitoring-service/issues/34.
    """
    state_db_sqlite.setup_db(1, get_random_address(), get_random_address())
    mr1 = get_monitor_request_for_same_channel(user=0)
    mr2 = get_monitor_request_for_same_channel(user=1)
    for mr in (mr1, mr2):
        state_db_sqlite.store_monitor_request(mr)

    all_monitor_requests = state_db_sqlite.monitor_requests
    assert len(all_monitor_requests) == 2


@pytest.fixture
def get_monitor_request_for_same_channel(get_random_address, get_random_privkey):
    keys = [get_random_privkey() for i in range(2)]
    token_network_address = get_random_address()

    channel_id = 1
    balance_hash_data = '0'

    def f(user=None):
        if user == 0:
            privkey = keys[0]
            privkey_non_closing = keys[1]
        else:
            privkey = keys[1]
            privkey_non_closing = keys[0]
        balance_proof = BalanceProof(
            channel_id,
            token_network_address,
            balance_hash=encode_hex(sha3(balance_hash_data.encode()))
        )
        balance_proof.signature = encode_hex(eth_sign(privkey, balance_proof.serialize_bin()))
        non_closing_signature = encode_hex(
            eth_sign(privkey_non_closing, balance_proof.serialize_bin()),
        )

        monitor_request = MonitorRequest(
            balance_proof,
            non_closing_signature,
            reward_amount=0,
            monitor_address=get_random_address(),
        )
        monitor_request.reward_proof_signature = encode_hex(
            eth_sign(privkey, monitor_request.serialize_reward_proof()),
        )
        return monitor_request
    return f
