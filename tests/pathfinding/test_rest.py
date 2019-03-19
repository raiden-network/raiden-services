import gc
from datetime import datetime, timedelta
from typing import List

import gevent
import pkg_resources
import requests
from eth_utils import encode_hex, to_normalized_address

import pathfinding_service.exceptions as exceptions
from pathfinding_service import PathfindingService
from pathfinding_service.api.rest import DEFAULT_MAX_PATHS, ServiceApi
from pathfinding_service.model import IOU, TokenNetwork
from raiden_libs.types import Address
from raiden_libs.utils import eth_sign, pack_data, private_key_to_address

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
    get_random_privkey,
):
    url = api_url + f'/{token_network_model.address}/paths'
    default_params = {
        'from': initiator_address,
        'to': target_address,
        'value': 5,
        'max_paths': 3,
    }

    def request_path_with(status_code=400, **kwargs):
        params = default_params.copy()
        params.update(kwargs)
        response = requests.post(url, json=params)
        assert response.status_code == status_code, response.json()
        return response

    response = requests.post(url)
    assert response.status_code == 400
    assert response.json()['errors'].startswith('Required parameters:')

    response = request_path_with(**{'from': 'notanaddress'})
    assert response.json()['errors'] == 'Invalid initiator address: notanaddress'

    response = request_path_with(to='notanaddress')
    assert response.json()['errors'] == 'Invalid target address: notanaddress'

    response = request_path_with(**{'from': to_normalized_address(initiator_address)})
    assert response.json()['errors'] == 'Initiator address not checksummed: {}'.format(
        to_normalized_address(initiator_address),
    )

    response = request_path_with(to=to_normalized_address(target_address))
    assert response.json()['errors'] == 'Target address not checksummed: {}'.format(
        to_normalized_address(target_address),
    )

    response = request_path_with(value=-10)
    assert response.json()['errors'] == 'Payment value must be non-negative: -10'

    response = request_path_with(max_paths=-1)
    assert response.json()['errors'] == 'Number of paths must be positive: -1'

    # Exemplary test for payment errors. Different errors are serialized the
    # same way in the rest API. Checking for specific errors is tested in
    # payment_tests.
    api_sut.pathfinding_service.service_fee = 1
    response = request_path_with()
    assert response.json()['error_code'] == exceptions.MissingIOU.error_code

    # with successful payment
    iou = make_iou(get_random_privkey(), api_sut.pathfinding_service.address)
    response = request_path_with(iou=iou, status_code=200)

    # kill all running greenlets
    gevent.killall(
        [obj for obj in gc.get_objects() if isinstance(obj, gevent.Greenlet)],
    )


def test_get_paths_path_validation(
    api_sut: ServiceApi,
    api_url: str,
):
    url = api_url + '/1234abc/paths'
    response = requests.post(url)
    assert response.status_code == 400
    assert response.json()['errors'] == 'Invalid token network address: 1234abc'

    url = api_url + '/df173a5173c3d0ae5ba11dae84470c5d3f1a8413/paths'
    response = requests.post(url)
    assert response.status_code == 400
    assert response.json()['errors'] == 'Token network address not checksummed: {}'.format(
        'df173a5173c3d0ae5ba11dae84470c5d3f1a8413',
    )

    url = api_url + '/0xdf173a5173c3d0ae5ba11dae84470c5d3f1a8413/paths'
    response = requests.post(url)
    assert response.status_code == 400
    assert response.json()['errors'] == 'Token network address not checksummed: {}'.format(
        '0xdf173a5173c3d0ae5ba11dae84470c5d3f1a8413',
    )

    url = api_url + '/0x0000000000000000000000000000000000000000/paths'
    response = requests.post(url)
    assert response.status_code == 400
    assert response.json()['errors'] == 'Unsupported token network: {}'.format(
        '0x0000000000000000000000000000000000000000',
    )
    # killen aller greenlets
    gevent.killall(
        [obj for obj in gc.get_objects() if isinstance(obj, gevent.Greenlet)],
    )


def test_get_paths(
    api_sut: ServiceApi,
    api_url: str,
    addresses: List[Address],
    token_network_model: TokenNetwork,
):
    url = api_url + f'/{token_network_model.address}/paths'

    data = {
        'from': addresses[0],
        'to': addresses[2],
        'value': 10,
        'max_paths': DEFAULT_MAX_PATHS,
    }
    response = requests.post(url, json=data)
    assert response.status_code == 200
    paths = response.json()['result']
    assert len(paths) == 1
    assert paths == [
        {
            'path': [addresses[0], addresses[1], addresses[2]],
            'estimated_fee': 0,
        },
    ]

    # check default value for num_path
    data = {
        'from': addresses[0],
        'to': addresses[2],
        'value': 10,
    }
    default_response = requests.post(url, json=data)
    assert default_response.json()['result'] == response.json()['result']

    # there is no connection between 0 and 5, this should return an error
    data = {
        'from': addresses[0],
        'to': addresses[5],
        'value': 10,
        'max_paths': 3,
    }
    response = requests.post(url, json=data)
    assert response.status_code == 400
    assert response.json()['errors'].startswith('No suitable path found for transfer from')

    # killen aller greenlets
    gevent.killall(
        [obj for obj in gc.get_objects() if isinstance(obj, gevent.Greenlet)],
    )


#
# tests for /info endpoint
#

def test_get_info(
    api_sut: ServiceApi,
    api_url: str,
    pathfinding_service_full_mock: PathfindingService,
):
    url = api_url + '/info'

    response = requests.get(url)
    assert response.status_code == 200
    assert response.json() == {
        'price_info': 0,
        'network_info': {
            'chain_id': pathfinding_service_full_mock.chain_id,
            'registry_address': pathfinding_service_full_mock.registry_address,
        },
        'settings': 'PLACEHOLDER FOR PATHFINDER SETTINGS',
        'version': pkg_resources.require('raiden-services')[0].version,
        'operator': 'PLACEHOLDER FOR PATHFINDER OPERATOR',
        'message': 'PLACEHOLDER FOR ADDITIONAL MESSAGE BY THE PFS',
    }
    # killen aller greenlets
    gevent.killall(
        [obj for obj in gc.get_objects() if isinstance(obj, gevent.Greenlet)],
    )


#
# tests for iou endpoint
#

def test_get_iou(
    api_sut: ServiceApi,
    api_url: str,
    pathfinding_service_full_mock: PathfindingService,
    token_network_model: TokenNetwork,
    get_random_privkey,
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
        params['signature'] = encode_hex(eth_sign(
            privkey,
            pack_data(
                ['address', 'address', 'string'],
                [params['sender'], params['receiver'], params['timestamp']],
            ),
        ))
        return params

    # Request without IOU in database
    params = make_params(datetime.utcnow())
    response = requests.get(url, params=params)
    assert response.status_code == 404, response.json()
    assert response.json() == {'last_iou': None}

    # Add IOU to database
    iou_dict = make_iou(privkey, api_sut.pathfinding_service.address)
    iou = IOU.Schema().load(iou_dict)[0]
    iou.claimed = False
    api_sut.pathfinding_service.database.upsert_iou(iou)

    # Is returned IOU the one save into the db?
    response = requests.get(url, params=params)
    assert response.status_code == 200, response.json()
    assert response.json()['last_iou'] == iou_dict

    # Invalid signatures must fail
    params['signature'] = hex(int(params['signature'], 16) + 1)
    response = requests.get(url, params=params)
    assert response.status_code == 400, response.json()
    assert response.json()['error_code'] == exceptions.InvalidSignature.error_code

    # Timestamp must no be too old to prevent replay attacks
    params = make_params(datetime.utcnow() - timedelta(days=1))
    response = requests.get(url, params=params)
    assert response.status_code == 400, response.json()
    assert response.json()['error_code'] == exceptions.RequestOutdated.error_code

    # kill all running greenlets
    gevent.killall(
        [obj for obj in gc.get_objects() if isinstance(obj, gevent.Greenlet)],
    )
