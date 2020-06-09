import pkg_resources
import requests
from eth_utils import to_checksum_address

from monitoring_service.api import MSApi
from monitoring_service.constants import DEFAULT_INFO_MESSAGE
from monitoring_service.service import MonitoringService


def test_get_info(api_url: str, ms_api_sut: MSApi, monitoring_service_mock: MonitoringService):
    monitoring_service_mock.context.min_reward = 123
    ms_api_sut.operator = "John Doe"
    url = api_url + "/info"

    token_network_registry_address = to_checksum_address(
        monitoring_service_mock.token_network_registry.address
    )
    user_deposit_address = to_checksum_address(
        monitoring_service_mock.context.user_deposit_contract.address
    )
    service_token_address = (
        monitoring_service_mock.context.user_deposit_contract.functions.token().call()
    )

    expected_response = {
        "price_info": 123,
        "network_info": {
            "chain_id": monitoring_service_mock.chain_id,
            "token_network_registry_address": token_network_registry_address,
            "user_deposit_address": user_deposit_address,
            "service_token_address": service_token_address,
            "confirmed_block": {"number": 0},
        },
        "version": pkg_resources.require("raiden-services")[0].version,
        "contracts_version": pkg_resources.require("raiden-contracts")[0].version,
        "operator": "John Doe",
        "message": DEFAULT_INFO_MESSAGE,
    }
    response = requests.get(url)
    assert response.status_code == 200
    response_json = response.json()
    del response_json["UTC"]
    assert response_json == expected_response

    # Test with a custom info message
    ms_api_sut.info_message = expected_response["message"] = "Other message"
    response = requests.get(url)
    assert response.status_code == 200
    response_json = response.json()
    del response_json["UTC"]
    assert response_json == expected_response
