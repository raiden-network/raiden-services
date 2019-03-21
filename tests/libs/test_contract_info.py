from raiden.utils.typing import Address, ChainID
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_libs.contract_info import START_BLOCK_ID, get_contract_addresses_and_start_block

DEFAULT_CHAIN_ID = ChainID(3)
DEFAULT_VERSION = '0.10.1'


def test_contract_info_defaults():
    infos = get_contract_addresses_and_start_block(
        chain_id=DEFAULT_CHAIN_ID,
        contracts_version=DEFAULT_VERSION,
    )
    assert infos is not None
    assert infos[CONTRACT_TOKEN_NETWORK_REGISTRY] == '0xde1fAa1385403f05C20a8ca5a0D5106163A35B6e'
    assert infos[CONTRACT_MONITORING_SERVICE] == '0x58c73CabCFB3c55B420E3F60a4b06098e9D1960E'
    assert infos[CONTRACT_USER_DEPOSIT] == '0x85F2c5eA50861DF5eA2EBd3651fAB091e14B849C'
    assert infos[START_BLOCK_ID] == 5235346


def test_contract_info_changed_safety_margin():
    infos = get_contract_addresses_and_start_block(
        chain_id=DEFAULT_CHAIN_ID,
        contracts_version=DEFAULT_VERSION,
        start_block_safety_margin=50,
    )
    assert infos is not None
    assert infos[CONTRACT_TOKEN_NETWORK_REGISTRY] == '0xde1fAa1385403f05C20a8ca5a0D5106163A35B6e'
    assert infos[CONTRACT_MONITORING_SERVICE] == '0x58c73CabCFB3c55B420E3F60a4b06098e9D1960E'
    assert infos[CONTRACT_USER_DEPOSIT] == '0x85F2c5eA50861DF5eA2EBd3651fAB091e14B849C'
    assert infos[START_BLOCK_ID] == 5235346 + 50


def test_contract_info_overwrite_defaults():
    address1 = Address('0x' + '1' * 40)
    address2 = Address('0x' + '2' * 40)
    address3 = Address('0x' + '3' * 40)
    infos = get_contract_addresses_and_start_block(
        chain_id=DEFAULT_CHAIN_ID,
        contracts_version=DEFAULT_VERSION,
        token_network_registry_address=address1,
        monitor_contract_address=address2,
        user_deposit_contract_address=address3,
        start_block=123,
    )
    assert infos is not None
    assert infos[CONTRACT_TOKEN_NETWORK_REGISTRY] == address1
    assert infos[CONTRACT_MONITORING_SERVICE] == address2
    assert infos[CONTRACT_USER_DEPOSIT] == address3
    assert infos[START_BLOCK_ID] == 123


def test_contract_info_returns_nothing_with_invalid_config():
    infos = get_contract_addresses_and_start_block(
        chain_id=ChainID(123456789),
        contracts_version=DEFAULT_VERSION,
    )
    assert infos is None


def test_contract_info_returns_nothing_with_partial_invalid_config():
    address1 = Address('0x' + '1' * 40)
    infos = get_contract_addresses_and_start_block(
        chain_id=ChainID(123456789),
        contracts_version=DEFAULT_VERSION,
        token_network_registry_address=address1,
    )
    assert infos is None


def test_contract_info_returns_user_defaults_with_full_config():
    address1 = Address('0x' + '1' * 40)
    address2 = Address('0x' + '2' * 40)
    address3 = Address('0x' + '3' * 40)
    infos = get_contract_addresses_and_start_block(
        chain_id=ChainID(123456789),
        contracts_version=DEFAULT_VERSION,
        token_network_registry_address=address1,
        monitor_contract_address=address2,
        user_deposit_contract_address=address3,
        start_block=123,
    )
    assert infos is not None
    assert infos[CONTRACT_TOKEN_NETWORK_REGISTRY] == address1
    assert infos[CONTRACT_MONITORING_SERVICE] == address2
    assert infos[CONTRACT_USER_DEPOSIT] == address3
    assert infos[START_BLOCK_ID] == 123
