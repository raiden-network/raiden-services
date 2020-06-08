import socket

import pytest


@pytest.fixture(scope="session")
def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("localhost", 0))  # binding to port 0 will choose a free socket
    port = sock.getsockname()[1]
    sock.close()
    return port
