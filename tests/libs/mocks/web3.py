from unittest.mock import Mock

from raiden_contracts.tests.utils import get_random_address


class ContractMock(Mock):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "address" not in kwargs:
            self.address = get_random_address()


class Web3Mock(Mock):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.eth.chainId = 61
        self.eth.blockNumber = 100

    def _get_child_mock(self, **kwargs):
        return Mock(**kwargs)
