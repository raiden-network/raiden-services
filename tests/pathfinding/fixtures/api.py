from itertools import count
from typing import Iterator

import psutil
import pytest

from pathfinding_service.api import ServiceApi
from pathfinding_service.config import API_PATH, DEFAULT_API_PORT


def get_free_port(address: str, initial_port: int):
    """Find an unused TCP port in a specified range. This should not
      be used in misson-critical applications - a race condition may
      occur if someone grabs the port before caller of this function
      has chance to use it.
      Parameters:
          address : an ip address of interface to use
          initial_port : port to start iteration with
      Return:
          Iterator that will return next unused port on a specified
          interface
    """

    try:
        # On OSX this function requires root privileges
        psutil.net_connections()
    except psutil.AccessDenied:
        return count(initial_port)

    def _unused_ports():
        for port in count(initial_port):
            # check if the port is being used
            connect_using_port = (
                conn
                for conn in psutil.net_connections()
                if hasattr(conn, "laddr") and conn.laddr[0] == address and conn.laddr[1] == port
            )

            # only generate unused ports
            if not any(connect_using_port):
                yield port

    return _unused_ports()


@pytest.fixture(scope="session")
def free_port() -> int:
    return next(get_free_port("localhost", DEFAULT_API_PORT))


@pytest.fixture(scope="session")
def api_url(free_port: int) -> str:
    return "http://localhost:{}{}".format(free_port, API_PATH)


@pytest.fixture
def api_sut(
    pathfinding_service_mock, free_port: int, populate_token_network_case_1: None
) -> Iterator[ServiceApi]:
    api = ServiceApi(pathfinding_service_mock)
    api.run(port=free_port)
    yield api
    api.stop()
