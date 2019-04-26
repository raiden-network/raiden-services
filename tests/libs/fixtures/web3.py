import json
import logging
from typing import Dict, List

import gevent
import pytest
from eth_account import Account
from tests.constants import KEYSTORE_FILE_NAME, KEYSTORE_PASSWORD

from raiden_contracts.contract_manager import ContractManager, contracts_precompiled_path
from raiden_libs.events import Event

log = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def wait_for_blocks(web3):
    """Returns a function that blocks until n blocks are mined"""

    def wait_for_blocks(n):
        web3.testing.mine(n)
        gevent.sleep()

    return wait_for_blocks


@pytest.fixture(scope="session")
def contracts_manager():
    """Overwrites the contracts_manager from raiden_contracts to use compiled contracts """
    return ContractManager(contracts_precompiled_path())


@pytest.fixture
def keystore_file(tmp_path) -> str:
    keystore_file = tmp_path / KEYSTORE_FILE_NAME

    account = Account.create()
    keystore_json = Account.encrypt(private_key=account.privateKey, password=KEYSTORE_PASSWORD)
    with open(keystore_file, "w") as fp:
        json.dump(keystore_json, fp)

    return keystore_file


@pytest.fixture
def mockchain(monkeypatch):
    state: Dict[str, List[List[Event]]] = dict(block_events=[])

    def get_events(
        web3, contract_manager, chain_state, to_block: int, query_ms=True
    ):  # pylint: disable=unused-argument
        from_block = chain_state.latest_known_block + 1
        blocks = state["block_events"][from_block : to_block + 1]
        events = [ev for block in blocks for ev in block]  # flatten
        return chain_state, events

    def set_events(events):
        state["block_events"] = events

    monkeypatch.setattr("monitoring_service.service.get_blockchain_events", get_events)
    monkeypatch.setattr("pathfinding_service.service.get_blockchain_events", get_events)
    return set_events
