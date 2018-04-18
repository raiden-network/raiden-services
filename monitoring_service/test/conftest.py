from gevent import monkey
monkey.patch_all()
from monitoring_service.test.fixtures import * # flake8: noqa
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger('evm.vm_state.SpuriousDragonVMState').setLevel(logging.WARN)
logging.getLogger('evm.vm.computation.Computation').setLevel(logging.WARN)
logging.getLogger('evm.vm.state.ByzantiumState').setLevel(logging.WARN)
