import gc
from datetime import datetime, timedelta
from typing import List

import gevent
import pkg_resources
import requests
from eth_utils import decode_hex, encode_hex, to_normalized_address

import pathfinding_service.exceptions as exceptions
from pathfinding_service.api import DEFAULT_MAX_PATHS, ServiceApi
from pathfinding_service.model import IOU, TokenNetwork
from raiden.utils.signer import LocalSigner
from raiden.utils.signing import pack_data
from raiden_contracts.tests.utils import get_random_privkey
from raiden_libs.types import Address
from raiden_libs.utils import private_key_to_address

from .test_payment import make_iou

ID_12 = 12
ID_123 = 123


#
# tests for /paths endpoint
#
def test_get_paths_validation(
    api_sut: ServiceApi,
    api_url: str,
    initiator_address: str,
    target_address: str,
    token_network_model: TokenNetwork,
):
    url = api_url + f'/{token_network_model.address}/paths'
    default_params = {'from': initiator_address, 'to': target_address, 'value': 5, 'max_paths': 3}

    def request_path_with(status_code=400, **kwargs):
        params = default_params.copy()
        params.update(kwargs)
        response = requests.post(url, json=params)
        assert response.status_code == status_code, response.json()
        return response

    response = requests.post(url)
    assert response.status_code == 400
    assert response.json()['errors'].startswith('JSON payload expected')

    for address in ['notanaddress', to_normalized_address(initiator_address)]:
        response = request_path_with(**{'from': address})
        assert response.json()['error_code'] == exceptions.InvalidRequest.error_code
        assert 'from' in response.json()['error_details']

        response = request_path_with(to=address)
        assert response.json()['error_code'] == exceptions.InvalidRequest.error_code
        assert 'to' in response.json()['error_details']

    response = request_path_with(value=-10)
    assert response.json()['error_code'] == exceptions.InvalidRequest.error_code
    assert 'value' in response.json()['error_details']

    response = request_path_with(max_paths=-1)
    assert response.json()['error_code'] == exceptions.InvalidRequest.error_code
    assert 'max_paths' in response.json()['error_details']

    # Exemplary test for payment errors. Different errors are serialized the
    # same way in the rest API. Checking for specific errors is tested in
    # payment_tests.
    api_sut.pathfinding_service.service_fee = 1
    response = request_path_with()
    assert response.json()['error_code'] == exceptions.MissingIOU.error_code

    # prepare iou for payment tests
    iou = make_iou(get_random_privkey(), api_sut.pathfinding_service.address)
    good_iou_dict = iou.Schema().dump(iou)[0]

    # malformed iou
    bad_iou_dict = good_iou_dict.copy()
    del bad_iou_dict['amount']
    response = request_path_with(iou=bad_iou_dict)
    assert response.json()['error_code'] == exceptions.InvalidRequest.error_code

    # bad signature
    bad_iou_dict = good_iou_dict.copy()
    bad_iou_dict['signature'] = hex(int(bad_iou_dict['signature'], 16) + 1)
    response = request_path_with(iou=bad_iou_dict)
    assert response.json()['error_code'] == exceptions.InvalidSignature.error_code

    # with successful payment
    response = request_path_with(iou=good_iou_dict, status_code=200)

    # kill all running greenlets
    gevent.killall([obj for obj in gc.get_objects() if isinstance(obj, gevent.Greenlet)])


def test_get_paths_path_validation(api_sut: ServiceApi, api_url: str):
    url = api_url + '/1234abc/paths'
    response = requests.post(url)
    assert response.status_code == 400
    assert response.json()['errors'] == 'Invalid token network address: 1234abc'

    url = api_url + '/df173a5173c3d0ae5ba11dae84470c5d3f1a8413/paths'
    response = requests.post(url)
    assert response.status_code == 400
    assert response.json()['errors'] == 'Token network address not checksummed: {}'.format(
        'df173a5173c3d0ae5ba11dae84470c5d3f1a8413'
    )

    url = api_url + '/0xdf173a5173c3d0ae5ba11dae84470c5d3f1a8413/paths'
    response = requests.post(url)
    assert response.status_code == 400
    assert response.json()['errors'] == 'Token network address not checksummed: {}'.format(
        '0xdf173a5173c3d0ae5ba11dae84470c5d3f1a8413'
    )

    url = api_url + '/0x0000000000000000000000000000000000000000/paths'
    response = requests.post(url)
    assert response.status_code == 400
    assert response.json()['errors'] == 'Unsupported token network: {}'.format(
        '0x0000000000000000000000000000000000000000'
    )
    # killen aller greenlets
    gevent.killall([obj for obj in gc.get_objects() if isinstance(obj, gevent.Greenlet)])


def test_get_paths(
    api_sut: ServiceApi, api_url: str, addresses: List[Address], token_network_model: TokenNetwork
):
    url = api_url + f'/{token_network_model.address}/paths'

    data = {'from': addresses[0], 'to': addresses[2], 'value': 10, 'max_paths': DEFAULT_MAX_PATHS}
    response = requests.post(url, json=data)
    assert response.status_code == 200
    paths = response.json()['result']
    assert len(paths) == 1
    assert paths == [{'path': [addresses[0], addresses[1], addresses[2]], 'estimated_fee': 0}]

    # check default value for num_path
    data = {'from': addresses[0], 'to': addresses[2], 'value': 10}
    default_response = requests.post(url, json=data)
    assert default_response.json()['result'] == response.json()['result']

    # impossible routes
    for source, dest in [
        (addresses[0], addresses[5]),  # no connection between 0 and 5
        ('0x' + '1' * 40, addresses[5]),  # source not in graph
        (addresses[0], '0x' + '1' * 40),  # dest not in graph
    ]:
        data = {'from': source, 'to': dest, 'value': 10, 'max_paths': 3}
        response = requests.post(url, json=data)
        assert response.status_code == 400
        assert response.json()['errors'].startswith('No suitable path found for transfer from')

    # killen aller greenlets
    gevent.killall([obj for obj in gc.get_objects() if isinstance(obj, gevent.Greenlet)])


#
# tests for /info endpoint
#


def test_get_info(api_sut: ServiceApi, api_url: str, pathfinding_service_mock):
    url = api_url + '/info'

    response = requests.get(url)
    assert response.status_code == 200
    assert response.json() == {
        'price_info': 0,
        'network_info': {
            'chain_id': pathfinding_service_mock.chain_id,
            'registry_address': pathfinding_service_mock.registry_address,
        },
        'settings': 'PLACEHOLDER FOR PATHFINDER SETTINGS',
        'version': pkg_resources.require('raiden-services')[0].version,
        'operator': 'PLACEHOLDER FOR PATHFINDER OPERATOR',
        'message': 'PLACEHOLDER FOR ADDITIONAL MESSAGE BY THE PFS',
    }
    # killen aller greenlets
    gevent.killall([obj for obj in gc.get_objects() if isinstance(obj, gevent.Greenlet)])


#
# tests for iou endpoint
#


def test_get_iou(
    api_sut: ServiceApi, api_url: str, pathfinding_service_mock, token_network_model: TokenNetwork
):
    privkey = get_random_privkey()
    sender = private_key_to_address(privkey)
    url = api_url + f'/{token_network_model.address}/payment/iou'

    def make_params(timestamp: datetime):
        params = {
            'sender': sender,
            'receiver': api_sut.pathfinding_service.address,
            'timestamp': timestamp.isoformat(),
        }
        local_signer = LocalSigner(private_key=decode_hex(privkey))
        params['signature'] = encode_hex(
            local_signer.sign(
                pack_data(
                    ['address', 'address', 'string'],
                    [params['sender'], params['receiver'], params['timestamp']],
                )
            )
        )
        return params

    # Request without IOU in database
    params = make_params(datetime.utcnow())
    response = requests.get(url, params=params)
    assert response.status_code == 404, response.json()
    assert response.json() == {'last_iou': None}

    # Add IOU to database
    iou = make_iou(privkey, api_sut.pathfinding_service.address)
    iou.claimed = False
    api_sut.pathfinding_service.database.upsert_iou(iou)

    # Is returned IOU the one save into the db?
    response = requests.get(url, params=params)
    assert response.status_code == 200, response.json()
    iou_dict = IOU.Schema(exclude=['claimed']).dump(iou)[0]
    assert response.json()['last_iou'] == iou_dict

    # Invalid signatures must fail
    params['signature'] = encode_hex((int(params['signature'], 16) + 1).to_bytes(65, 'big'))
    response = requests.get(url, params=params)
    assert response.status_code == 400, response.json()
    assert response.json()['error_code'] == exceptions.InvalidSignature.error_code

    # Timestamp must no be too old to prevent replay attacks
    params = make_params(datetime.utcnow() - timedelta(days=1))
    response = requests.get(url, params=params)
    assert response.status_code == 400, response.json()
    assert response.json()['error_code'] == exceptions.RequestOutdated.error_code

    # kill all running greenlets
    gevent.killall([obj for obj in gc.get_objects() if isinstance(obj, gevent.Greenlet)])
