import pytest

from tests.pathfinding.fixtures import *  # isort:skip # noqa


def pytest_addoption(parser):
    parser.addoption(
        "--faucet-private-key",
        default='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        dest='faucet_private_key',
        help="The private key to an address with sufficient tokens to run the tests.",
    )


@pytest.fixture(autouse=True)
def unregister_error_handler():
    from raiden_libs.gevent_error_handler import unregister_error_handler

    unregister_error_handler()
