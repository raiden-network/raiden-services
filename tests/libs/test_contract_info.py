import pytest
from eth_utils import decode_hex

from raiden_common.utils.typing import Address, ChainID
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_libs.contract_info import get_contract_addresses_and_start_block

DEFAULT_CHAIN_ID = ChainID(5)
DEFAULT_VERSION = "0.37.0"


def test_contract_info_defaults():
    infos, start_block = get_contract_addresses_and_start_block(
        chain_id=DEFAULT_CHAIN_ID,
        contracts=[
            CONTRACT_TOKEN_NETWORK_REGISTRY,
            CONTRACT_MONITORING_SERVICE,
            CONTRACT_USER_DEPOSIT,
        ],
        address_overwrites={},
        contracts_version=DEFAULT_VERSION,
    )
    assert infos is not None
    assert infos[CONTRACT_TOKEN_NETWORK_REGISTRY] == decode_hex(
        "0x5a5cf4a63022f61f1506d1a2398490c2e8dfbb98"
    )
    assert infos[CONTRACT_MONITORING_SERVICE] == decode_hex(
        "0x20e8e5181000e60799a523a2023d630868f378fd"
    )
    assert infos[CONTRACT_USER_DEPOSIT] == decode_hex("0x0794f09913aa8c77c8c5bdd1ec4bb51759ee0cc5")
    assert start_block == 2723614


def test_contract_info_overwrite_defaults():
    address1 = Address(bytes([1] * 20))
    address2 = Address(bytes([2] * 20))
    address3 = Address(bytes([3] * 20))
    infos, start_block = get_contract_addresses_and_start_block(
        chain_id=DEFAULT_CHAIN_ID,
        contracts_version=DEFAULT_VERSION,
        contracts=[
            CONTRACT_TOKEN_NETWORK_REGISTRY,
            CONTRACT_MONITORING_SERVICE,
            CONTRACT_USER_DEPOSIT,
        ],
        address_overwrites={
            CONTRACT_TOKEN_NETWORK_REGISTRY: address1,
            CONTRACT_MONITORING_SERVICE: address2,
            CONTRACT_USER_DEPOSIT: address3,
        },
    )
    assert infos is not None
    assert infos[CONTRACT_TOKEN_NETWORK_REGISTRY] == address1
    assert infos[CONTRACT_MONITORING_SERVICE] == address2
    assert infos[CONTRACT_USER_DEPOSIT] == address3
    assert start_block == 0


def test_invalid_chain_id():
    with pytest.raises(SystemExit):
        get_contract_addresses_and_start_block(
            chain_id=ChainID(123456789),
            contracts_version=DEFAULT_VERSION,
            contracts=[],
            address_overwrites={},
        )
