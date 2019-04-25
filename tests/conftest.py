from gevent import monkey, config  # isort:skip # noqa

# there were some issues with the 'thread' resolver, remove it from the options
config.resolver = ["dnspython", "ares", "block"]  # noqa
monkey.patch_all()  # isort:skip # noqa

import gc

import gevent
import pytest

from raiden_contracts.tests.fixtures import *  # noqa

from .libs.fixtures import *  # noqa


def _get_running_greenlets():
    return [
        obj
        for obj in gc.get_objects()
        if isinstance(obj, gevent.Greenlet) and obj and not obj.dead
    ]


@pytest.fixture(autouse=True)
def no_greenlets_left():
    """ Check that no greenlets run at the end of a test

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
