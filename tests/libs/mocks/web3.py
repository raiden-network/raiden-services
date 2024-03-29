from unittest.mock import Mock

from raiden_contracts.tests.utils import get_random_address
from tests.constants import TEST_CHAIN_ID


class ContractMock(Mock):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "address" not in kwargs:
            self.address = get_random_address()


class Web3Mock(Mock):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.eth.chain_id = TEST_CHAIN_ID
        self.eth.block_number = 100

    def _get_child_mock(self, **kwargs):  # pylint: disable=arguments-differ
        return Mock(**kwargs)
