# -*- coding: utf-8 -*-
import pytest
import random

from raiden_libs.contracts import ContractManager


def test_contract_manager():
    manager = ContractManager('contracts/contracts_12032018.json')

    assert manager.get_contract_abi('CustomToken')
    with pytest.raises(KeyError):
        manager.get_contract_abi('SomeName')

    assert manager.get_event_abi('TokenNetwork', 'ChannelOpened')
    with pytest.raises(KeyError):
        manager.get_event_abi('TokenNetwork', 'NonExistant')


def test_deploy_multiple_tokens(add_and_register_token):
    """Deploy and register $DEPLOY_TOKENS tokens in a TokenNetworksRegistry"""
    DEPLOY_TOKENS = 10
    token_list = [
        (
            random.randint(100, 1000000),
            random.randint(1, 25),
            'TK' + chr(i + 0x41),
            'TT' + chr(i + 0x41)
        )
        for i in range(DEPLOY_TOKENS)
    ]
    token_contracts = [
        add_and_register_token(*x)
        for x in token_list
    ]
    assert len(token_contracts) == DEPLOY_TOKENS
