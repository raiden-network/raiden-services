# -*- coding: utf-8 -*-
import random


def test_deploy_multiple_tokens(add_and_register_token):
    """Deploy and register $DEPLOY_TOKENS tokens in a TokenNetworksRegistry"""
    DEPLOY_TOKENS = 10
    token_list = [
        (
            random.randint(100, 1000000),
            random.randint(1, 25),
            'TK' + chr(i + 0x41),
            'TT' + chr(i + 0x41),
        )
        for i in range(DEPLOY_TOKENS)
    ]
    token_contracts = [
        add_and_register_token(*x)
        for x in token_list
    ]
    assert len(token_contracts) == DEPLOY_TOKENS
