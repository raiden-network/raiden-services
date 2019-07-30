# pylint: disable=redefined-outer-name
import socket
from typing import Dict, Iterator

import pytest

from pathfinding_service.api import ServiceApi
from pathfinding_service.config import API_PATH
from raiden.network.transport.matrix import AddressReachability
from raiden.utils.typing import Address


@pytest.fixture(scope="session")
def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("localhost", 0))  # binding to port 0 will choose a free socket
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture(scope="session")
def api_url(free_port: int) -> str:
    return "http://localhost:{}{}".format(free_port, API_PATH)


@pytest.fixture
def api_sut(
    pathfinding_service_mock,
    address_to_reachability: Dict[Address, AddressReachability],
    free_port: int,
    populate_token_network_case_1,  # pylint: disable=unused-argument
) -> Iterator[ServiceApi]:
    pathfinding_service_mock.address_to_reachability = address_to_reachability
    api = ServiceApi(
        pathfinding_service=pathfinding_service_mock,
        one_to_n_address=Address(bytes([1] * 20)),
        operator="",
        info_message="",
    )
    api.run(port=free_port)
    yield api
    api.stop()


@pytest.fixture
def api_sut_with_debug(
    pathfinding_service_mock,
    address_to_reachability: Dict[Address, AddressReachability],
    free_port: int,
    populate_token_network_case_1,  # pylint: disable=unused-argument
) -> Iterator[ServiceApi]:
    pathfinding_service_mock.address_to_reachability = address_to_reachability
    api = ServiceApi(
        pathfinding_service=pathfinding_service_mock,
        one_to_n_address=Address(bytes([1] * 20)),
        debug_mode=True,
        operator="",
        info_message="",
    )
    api.run(port=free_port)
    yield api
    api.stop()
