# pylint: disable=redefined-outer-name
from typing import Iterator

import pytest

from pathfinding_service.api import PFSApi
from pathfinding_service.constants import API_PATH
from pathfinding_service.service import PathfindingService
from raiden.utils.typing import Address
from raiden_libs.constants import DEFAULT_API_HOST

from ..utils import SimpleReachabilityContainer


@pytest.fixture(scope="session")
def api_url(free_port: int) -> str:
    return "http://localhost:{}{}".format(free_port, API_PATH)


@pytest.fixture
def api_sut(
    pathfinding_service_mock: PathfindingService,
    reachability_state: SimpleReachabilityContainer,
    free_port: int,
    populate_token_network_case_1,  # pylint: disable=unused-argument
) -> Iterator[PFSApi]:
    pathfinding_service_mock.matrix_listener.user_manager = reachability_state
    api = PFSApi(
        pathfinding_service=pathfinding_service_mock,
        one_to_n_address=Address(bytes([1] * 20)),
        operator="",
    )
    api.run(host=DEFAULT_API_HOST, port=free_port)
    yield api
    api.stop()


@pytest.fixture
def api_sut_with_debug(
    pathfinding_service_mock,
    reachability_state: SimpleReachabilityContainer,
    free_port: int,
    populate_token_network_case_1,  # pylint: disable=unused-argument
) -> Iterator[PFSApi]:
    pathfinding_service_mock.matrix_listener.user_manager = reachability_state
    api = PFSApi(
        pathfinding_service=pathfinding_service_mock,
        one_to_n_address=Address(bytes([1] * 20)),
        debug_mode=True,
        operator="",
        info_message="",
    )
    api.run(host=DEFAULT_API_HOST, port=free_port)
    yield api
    api.stop()
