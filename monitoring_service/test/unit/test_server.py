import pytest

from monitoring_service import MonitoringService
from monitoring_service.exceptions import ServiceNotRegistered
from monitoring_service.utils import is_service_registered, register_service
from raiden_libs.utils import private_key_to_address


def test_server_registration(
    faucet_address,
    server_private_key,
    blockchain,
    dummy_transport,
    state_db_mock,
    web3,
    standard_token_contract,
    token_network_registry_contract,
    monitoring_service_contract,
    send_funds,
    contracts_manager,
):
    """Test two scenarios - instantiating a non-registered server (this should fail),
    and registering it and instantiating again"""
    # instantiation will fail - MS is not registered
    with pytest.raises(ServiceNotRegistered):
        MonitoringService(
            web3=web3,
            contract_manager=contracts_manager,
            private_key=server_private_key,
            transport=dummy_transport,
            state_db=state_db_mock,
            registry_address=token_network_registry_contract.address,
            monitor_contract_address=monitoring_service_contract.address,
        )

    # give some tokens to the MS
    server_address = private_key_to_address(server_private_key)
    send_funds(server_address)
    # register MS
    register_service(
        web3,
        contracts_manager,
        monitoring_service_contract.address,
        server_private_key,
    )

    # check if registration succeeded
    assert is_service_registered(
        web3,
        contracts_manager,
        monitoring_service_contract.address,
        server_address,
    )
    # now instantiation will proceed
    ms = MonitoringService(
        web3=web3,
        contract_manager=contracts_manager,
        private_key=server_private_key,
        transport=dummy_transport,
        state_db=state_db_mock,
        registry_address=token_network_registry_contract.address,
        monitor_contract_address=monitoring_service_contract.address,
    )
    assert ms is not None
