# -*- coding: utf-8 -*-
import pytest

from raiden_libs.contracts import ContractManager


def test_contract_manager():
    manager = ContractManager('contracts/contracts_12032018.json')

    assert manager.get_contract_abi('CustomToken')
    with pytest.raises(KeyError):
        manager.get_contract_abi('SomeName')

    assert manager.get_event_abi('TokenNetwork', 'ChannelOpened')
    with pytest.raises(KeyError):
        manager.get_event_abi('TokenNetwork', 'NonExistant')
