"""
For some reason isort changes the behaviour of this file. Might have something
to do with monkey.patch_all.

isort:skip_file
"""
from gevent import monkey  # isort:skip
monkey.patch_all()         # isort:skip
from raiden_libs.test.fixtures import *        # noqa
from raiden_libs.test.fixtures.web3 import *        # noqa
from raiden_libs.test.fixtures.address import *     # noqa
from raiden_libs.test.fixtures.client import *      # noqa
from raiden_contracts.tests.fixtures import *   # noqa
from monitoring_service.test.fixtures import *  # noqa
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger('eth.vm_state.SpuriousDragonVMState').setLevel(logging.WARN)
logging.getLogger('eth.vm.computation.Computation').setLevel(logging.WARN)
logging.getLogger('eth.vm.state.ByzantiumState').setLevel(logging.WARN)
logging.getLogger('eth.gas.GasMeter').setLevel(logging.WARN)
