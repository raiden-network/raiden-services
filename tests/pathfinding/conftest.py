from tests.pathfinding.fixtures import *  # isort:skip # noqa


def pytest_addoption(parser):
    parser.addoption(
        "--faucet-private-key",
        default="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        dest="faucet_private_key",
        help="The private key to an address with sufficient tokens to run the tests.",
    )
