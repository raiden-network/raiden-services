import requests


def test_rest_api(monitoring_service, rest_api, get_random_bp):
    ret = requests.get('http://localhost:5001/api/1/balance_proofs')
    assert ret.json() == []
    msg = get_random_bp()
    monitoring_service.transport.send_message(msg)
    ret = requests.get('http://localhost:5001/api/1/balance_proofs')
    assert len([x for x in ret.json() if x['channel_address'] == msg.channel_address]) == 1
