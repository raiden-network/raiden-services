from gevent import monkey
monkey.patch_all()
from raiden_libs.test.fixtures import *        # noqa
from raiden_libs.test.fixtures.web3 import *        # noqa
from raiden_libs.test.fixtures.address import *     # noqa
from raiden_libs.test.fixtures.client import *      # noqa
from raiden_contracts.tests.fixtures import *   # noqa
from monitoring_service.test.fixtures import * # flake8: noqa
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger('evm.vm_state.SpuriousDragonVMState').setLevel(logging.WARN)
logging.getLogger('evm.vm.computation.Computation').setLevel(logging.WARN)
logging.getLogger('evm.vm.state.ByzantiumState').setLevel(logging.WARN)
logging.getLogger('evm.gas.GasMeter').setLevel(logging.WARN)
