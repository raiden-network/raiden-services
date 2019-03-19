import gc
from typing import List

import gevent
import pkg_resources
import requests
from eth_utils import to_normalized_address

from pathfinding_service import PathfindingService
from pathfinding_service.api.rest import DEFAULT_MAX_PATHS, ServiceApi
from pathfinding_service.model import TokenNetwork
from raiden_libs.types import Address

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
    default_params = {
        'from': initiator_address,
        'to': target_address,
        'value': 5,
        'max_paths': 3,
    }

    def request_path_with(**kwargs):
        params = default_params.copy()
        params.update(kwargs)
        response = requests.post(url, data=params)
        assert response.status_code == 400
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
    response = requests.post(url, data=data)
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
    default_response = requests.post(url, data=data)
    assert default_response.json()['result'] == response.json()['result']

    # there is no connection between 0 and 5, this should return an error
    data = {
        'from': addresses[0],
        'to': addresses[5],
        'value': 10,
        'max_paths': 3,
    }
    response = requests.post(url, data=data)
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
