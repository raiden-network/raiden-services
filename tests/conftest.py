from raiden_libs.test.fixtures.address import *  # noqa
from raiden_libs.test.fixtures.contracts import *  # noqa
from raiden_libs.test.fixtures.client import *  # noqa
from raiden_libs.test.fixtures.web3 import *  # noqa

from .fixture_overwrites import *  # noqa


def pytest_addoption(parser):
    parser.addoption(
        "--no-tester",
        action="store_false",
        default=True,
        dest='use_tester',
        help="Use a real RPC endpoint instead of the tester chain."
    )
