# pylint: disable=unused-import
from gevent import config  # isort:skip # noqa

# there were some issues with the 'thread' resolver, remove it from the options
config.resolver = ["dnspython", "ares", "block"]  # noqa

import gc

import gevent
import pytest

from raiden_contracts.tests.fixtures import (  # noqa
    auto_revert_chain,
    channel_participant_deposit_limit,
    create_account,
    create_channel,
    create_service_account,
    custom_token,
    custom_token_factory,
    deploy_contract_txhash,
    deploy_tester_contract,
    deposit_to_udc,
    ethereum_tester,
    get_accounts,
    get_private_key,
    monitoring_service_external,
    one_to_n_contract,
    patch_genesis_gas_limit,
    register_token_network,
    secret_registry_contract,
    service_registry,
    token_args,
    token_network,
    token_network_deposit_limit,
    token_network_libs,
    token_network_registry_constructor_args,
    token_network_registry_contract,
    token_network_utils_library,
    uninitialized_user_deposit_contract,
    user_deposit_contract,
    user_deposit_whole_balance_limit,
    web3,
)
from raiden_libs.cli import start_profiler

from .libs.fixtures import *  # noqa

# from raiden_contracts.tests.fixtures import *  # isort:skip


def pytest_addoption(parser):
    # Using this will create a stack profile for all selected tests. If you
    # want to profile only a single test, use pytest to limit the test
    # selection.
    # Use https://github.com/brendangregg/FlameGraph to view the results.
    parser.addoption("--flamegraph", default=None, help="Dir in which to save stack profile.")


@pytest.fixture(autouse=True, scope="session")
def flamegraph_profiler(request):
    profiler = start_profiler(request.config.option.flamegraph)

    yield

    if profiler is not None:
        profiler.stop()


def _get_running_greenlets():
    return [
        obj
        for obj in gc.get_objects()
        if isinstance(obj, gevent.Greenlet) and obj and not obj.dead
    ]


@pytest.fixture(autouse=True)
def no_greenlets_left():
    """Check that no greenlets run at the end of a test

    It's easy to forget to properly stop all greenlets or to introduce a subtle
    bug in the shutdown process. Left over greenlets will cause other tests to
    fail, which is hard to track down. To avoid this, this function will look
    for such greenlets after each test and make the test fail if any greenlet
    is still running.
    """
    yield
    tasks = _get_running_greenlets()
    # give all tasks the chance to clean themselves up
    for task in tasks:
        if hasattr(task, "stop"):
            task.stop()
    gevent.joinall(tasks, timeout=1)
    tasks = _get_running_greenlets()
    if tasks:
        print("The following greenlets are still running after the test:", tasks)
    assert not tasks, "All greenlets must be stopped at the end of a test."
