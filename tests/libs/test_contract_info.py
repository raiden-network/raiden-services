import pytest

from raiden.utils.typing import ChainID
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_libs.contract_info import get_contract_addresses_and_start_block
from raiden_libs.types import Address

DEFAULT_CHAIN_ID = ChainID(3)
DEFAULT_VERSION = "0.10.1"


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
    assert infos[CONTRACT_TOKEN_NETWORK_REGISTRY] == "0xde1fAa1385403f05C20a8ca5a0D5106163A35B6e"
    assert infos[CONTRACT_MONITORING_SERVICE] == "0x58c73CabCFB3c55B420E3F60a4b06098e9D1960E"
    assert infos[CONTRACT_USER_DEPOSIT] == "0x85F2c5eA50861DF5eA2EBd3651fAB091e14B849C"
    assert start_block == 5235446


def test_contract_info_overwrite_defaults():
    address1 = Address("0x" + "1" * 40)
    address2 = Address("0x" + "2" * 40)
    address3 = Address("0x" + "3" * 40)
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
