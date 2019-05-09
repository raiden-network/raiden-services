from datetime import datetime, timedelta
from typing import List
from uuid import uuid4

import pkg_resources
import pytest
import requests
from eth_utils import decode_hex, encode_hex, to_bytes, to_checksum_address, to_normalized_address
from tests.pathfinding.test_database import db_has_feedback_for

import pathfinding_service.exceptions as exceptions
from pathfinding_service.api import DEFAULT_MAX_PATHS, ServiceApi
from pathfinding_service.model import IOU, TokenNetwork
from pathfinding_service.model.feedback import FeedbackToken
from raiden.utils.signer import LocalSigner
from raiden.utils.signing import pack_data
from raiden.utils.typing import Address, BlockNumber, Signature, TokenAmount
from raiden_contracts.tests.utils import get_random_privkey
from raiden_libs.utils import private_key_to_address

from .test_payment import make_iou

ID_12 = 12
ID_123 = 123


#
# tests for /_debug endpoint
#
@pytest.mark.usefixtures("api_sut")
def test_get_paths_via_debug_endpoint_with_debug_disabled(
    api_url: str, addresses: List[Address], token_network_model: TokenNetwork
):
    url_debug = api_url + f"/_debug/routes/{token_network_model.address}/{addresses[0]}"

    # now there must be a debug endpoint for that specific route
    response_debug = requests.get(url_debug)
    assert response_debug.status_code == 404


@pytest.mark.usefixtures("api_sut_with_debug")
def test_get_paths_via_debug_endpoint(
    api_url: str, addresses: List[Address], token_network_model: TokenNetwork
):
    hex_addrs = [to_checksum_address(addr) for addr in addresses]
    token_network_address = to_checksum_address(token_network_model.address)
    url_debug = api_url + f"/_debug/routes/{token_network_address}/{hex_addrs[0]}"
    url_debug_incl_requested_target = (
        api_url + f"/_debug/routes/{token_network_address}/{hex_addrs[0]}/{hex_addrs[2]}"
    )
    url_debug_incl_unrequested_target = (
        api_url + f"/_debug/routes/{token_network_address}/{hex_addrs[0]}/{hex_addrs[3]}"
    )

    response = requests.post(
        api_url + f"/{token_network_address}/paths",
        json={
            "from": hex_addrs[0],
            "to": hex_addrs[2],
            "value": 10,
            "max_paths": DEFAULT_MAX_PATHS,
        },
    )
    assert response.status_code == 200
    paths = response.json()["result"]
    assert len(paths) == 1
    assert paths == [{"path": [hex_addrs[0], hex_addrs[1], hex_addrs[2]], "estimated_fee": 0}]

    # now there must be a debug endpoint for that specific route
    response_debug = requests.get(url_debug)
    assert response_debug.status_code == 200
    request_count = response_debug.json()["request_count"]
    assert request_count == 1
    responses = response_debug.json()["responses"]
    assert responses == [
        {
            "source": hex_addrs[0],
            "target": hex_addrs[2],
            "routes": [{"path": [hex_addrs[0], hex_addrs[1], hex_addrs[2]], "estimated_fee": 0}],
        }
    ]

    # now there must be a debug endpoint for that specific route and that specific target
    response_debug_incl_target = requests.get(url_debug_incl_requested_target)
    assert response_debug_incl_target.status_code == 200
    request_count = response_debug_incl_target.json()["request_count"]
    assert request_count == 1
    responses = response_debug.json()["responses"]
    assert responses == [
        {
            "source": hex_addrs[0],
            "target": hex_addrs[2],
            "routes": [{"path": [hex_addrs[0], hex_addrs[1], hex_addrs[2]], "estimated_fee": 0}],
        }
    ]

    # when requesting info for a target that was no path requested for
    response_debug_incl_unrequested_target = requests.get(url_debug_incl_unrequested_target)
    assert response_debug_incl_unrequested_target.status_code == 200
    request_count = response_debug_incl_unrequested_target.json()["request_count"]
    assert request_count == 0
    responses = response_debug_incl_unrequested_target.json()["responses"]
    assert responses == []


def test_get_ious_via_debug_endpoint(
    api_sut_with_debug: ServiceApi, api_url: str, addresses: List[Address]
):
    hex_addrs = [to_checksum_address(addr) for addr in addresses]
    iou = IOU(
        sender=addresses[0],
        receiver=addresses[4],
        amount=TokenAmount(111),
        expiration_block=BlockNumber(7619644),
        signature=Signature(
            to_bytes(hexstr="118a93e9fd0a3a1c3d6edbad194b5c9d95715c754881d80e23e985793b1e13de")
        ),
        claimed=False,
    )
    api_sut_with_debug.pathfinding_service.database.upsert_iou(iou)

    # now there must be an iou debug endpoint for a request of a sender in the database
    url_iou_debug = api_url + f"/_debug/ious/{hex_addrs[0]}"
    response_debug = requests.get(url_iou_debug)
    assert response_debug.status_code == 200
    response_iou = response_debug.json()
    assert response_iou == {"sender": hex_addrs[0], "amount": 111, "expiration_block": 7619644}

    # but there is no iou debug endpoint for a request of a sender not in the database
    url_iou_debug = api_url + f"/_debug/ious/{hex_addrs[1]}"
    response_debug = requests.get(url_iou_debug)
    assert response_debug.status_code == 200
    ious = response_debug.json()
    assert ious == {}


#
# tests for /paths endpoint
#
def test_get_paths_validation(
    api_sut: ServiceApi, api_url: str, addresses: List[Address], token_network_model: TokenNetwork
):
    initiator_address = to_checksum_address(addresses[0])
    target_address = to_checksum_address(addresses[1])
    url = api_url + "/" + to_checksum_address(token_network_model.address) + "/paths"
    default_params = {"from": initiator_address, "to": target_address, "value": 5, "max_paths": 3}

    def request_path_with(status_code=400, **kwargs):
        params = default_params.copy()
        params.update(kwargs)
        response = requests.post(url, json=params)
        assert response.status_code == status_code, response.json()
        return response

    response = requests.post(url)
    assert response.status_code == 400
    assert response.json()["errors"].startswith("JSON payload expected")

    for address in ["notanaddress", to_normalized_address(initiator_address)]:
        response = request_path_with(**{"from": address})
        assert response.json()["error_code"] == exceptions.InvalidRequest.error_code
        assert "from" in response.json()["error_details"]

        response = request_path_with(to=address)
        assert response.json()["error_code"] == exceptions.InvalidRequest.error_code
        assert "to" in response.json()["error_details"]

    response = request_path_with(value=-10)
    assert response.json()["error_code"] == exceptions.InvalidRequest.error_code
    assert "value" in response.json()["error_details"]

    response = request_path_with(max_paths=-1)
    assert response.json()["error_code"] == exceptions.InvalidRequest.error_code
    assert "max_paths" in response.json()["error_details"]

    # successful request without payment
    request_path_with(status_code=200)

    # Exemplary test for payment errors. Different errors are serialized the
    # same way in the rest API. Checking for specific errors is tested in
    # payment_tests.
    api_sut.service_fee = TokenAmount(1)
    response = request_path_with()
    assert response.json()["error_code"] == exceptions.MissingIOU.error_code

    # prepare iou for payment tests
    iou = make_iou(get_random_privkey(), api_sut.pathfinding_service.address)
    good_iou_dict = iou.Schema().dump(iou)[0]

    # malformed iou
    bad_iou_dict = good_iou_dict.copy()
    del bad_iou_dict["amount"]
    response = request_path_with(iou=bad_iou_dict)
    assert response.json()["error_code"] == exceptions.InvalidRequest.error_code

    # bad signature
    bad_iou_dict = good_iou_dict.copy()
    bad_iou_dict["signature"] = "0x" + "1" * 130
    response = request_path_with(iou=bad_iou_dict)
    assert response.json()["error_code"] == exceptions.InvalidSignature.error_code

    # with successful payment
    request_path_with(iou=good_iou_dict, status_code=200)


@pytest.mark.usefixtures("api_sut")
def test_get_paths_path_validation(api_url: str):
    for url in [
        "/1234abc/paths",
        "/df173a5173c3d0ae5ba11dae84470c5d3f1a8413/paths",
        "/0xdf173a5173c3d0ae5ba11dae84470c5d3f1a8413/paths",
    ]:
        response = requests.post(api_url + url)
        assert response.status_code == 400
        assert response.json()["error_code"] == exceptions.InvalidTokenNetwork.error_code

    url = api_url + "/0x0000000000000000000000000000000000000000/paths"
    response = requests.post(url)
    assert response.status_code == 400
    assert response.json()["error_code"] == exceptions.UnsupportedTokenNetwork.error_code


@pytest.mark.usefixtures("api_sut")
def test_get_paths(api_url: str, addresses: List[Address], token_network_model: TokenNetwork):
    hex_addrs = [to_checksum_address(addr) for addr in addresses]
    url = api_url + "/" + to_checksum_address(token_network_model.address) + "/paths"

    data = {"from": hex_addrs[0], "to": hex_addrs[2], "value": 10, "max_paths": DEFAULT_MAX_PATHS}
    response = requests.post(url, json=data)
    assert response.status_code == 200
    paths = response.json()["result"]
    assert len(paths) == 1
    assert paths == [{"path": [hex_addrs[0], hex_addrs[1], hex_addrs[2]], "estimated_fee": 0}]

    # check default value for num_path
    data = {"from": hex_addrs[0], "to": hex_addrs[2], "value": 10}
    default_response = requests.post(url, json=data)
    assert default_response.json()["result"] == response.json()["result"]

    # impossible routes
    for source, dest in [
        (hex_addrs[0], hex_addrs[5]),  # no connection between 0 and 5
        ("0x" + "1" * 40, hex_addrs[5]),  # source not in graph
        (hex_addrs[0], "0x" + "1" * 40),  # dest not in graph
    ]:
        data = {"from": source, "to": dest, "value": 10, "max_paths": 3}
        response = requests.post(url, json=data)
        assert response.status_code == 404
        assert response.json()["error_code"] == exceptions.NoRouteFound.error_code


#
# tests for /info endpoint
#
def test_get_info(api_url: str, api_sut, pathfinding_service_mock):
    api_sut.service_fee = 123
    url = api_url + "/info"

    response = requests.get(url)
    assert response.status_code == 200
    assert response.json() == {
        "price_info": 123,
        "network_info": {
            "chain_id": pathfinding_service_mock.chain_id,
            "registry_address": to_checksum_address(pathfinding_service_mock.registry_address),
        },
        "settings": "PLACEHOLDER FOR PATHFINDER SETTINGS",
        "version": pkg_resources.require("raiden-services")[0].version,
        "operator": "PLACEHOLDER FOR PATHFINDER OPERATOR",
        "message": "PLACEHOLDER FOR ADDITIONAL MESSAGE BY THE PFS",
        "payment_address": to_checksum_address(pathfinding_service_mock.address),
    }


#
# tests for /payment/iou endpoint
#
def test_get_iou(api_sut: ServiceApi, api_url: str, token_network_model: TokenNetwork):
    privkey = get_random_privkey()
    sender = decode_hex(private_key_to_address(privkey))
    url = api_url + f"/{to_checksum_address(token_network_model.address)}/payment/iou"

    def make_params(timestamp: datetime):
        params = {
            "sender": to_checksum_address(sender),
            "receiver": to_checksum_address(api_sut.pathfinding_service.address),
            "timestamp": timestamp.isoformat(),
        }
        local_signer = LocalSigner(private_key=decode_hex(privkey))
        params["signature"] = encode_hex(
            local_signer.sign(
                pack_data(
                    ["address", "address", "string"],
                    [params["sender"], params["receiver"], params["timestamp"]],
                )
            )
        )
        return params

    # Request without IOU in database
    params = make_params(datetime.utcnow())
    response = requests.get(url, params=params)
    assert response.status_code == 404, response.json()
    assert response.json() == {"last_iou": None}

    # Add IOU to database
    iou = make_iou(privkey, api_sut.pathfinding_service.address)
    iou.claimed = False
    api_sut.pathfinding_service.database.upsert_iou(iou)

    # Is returned IOU the one save into the db?
    response = requests.get(url, params=params)
    assert response.status_code == 200, response.json()
    iou_dict = IOU.Schema(exclude=["claimed"]).dump(iou)[0]
    assert response.json()["last_iou"] == iou_dict

    # Invalid signatures must fail
    params["signature"] = encode_hex((int(params["signature"], 16) + 1).to_bytes(65, "big"))
    response = requests.get(url, params=params)
    assert response.status_code == 400, response.json()
    assert response.json()["error_code"] == exceptions.InvalidSignature.error_code

    # Timestamp must no be too old to prevent replay attacks
    params = make_params(datetime.utcnow() - timedelta(days=1))
    response = requests.get(url, params=params)
    assert response.status_code == 400, response.json()
    assert response.json()["error_code"] == exceptions.RequestOutdated.error_code


#
# tests for /feedback endpoint
#
def test_feedback(api_sut: ServiceApi, api_url: str, token_network_model: TokenNetwork):
    database = api_sut.pathfinding_service.database
    default_path_hex = ["0x" + "1" * 40, "0x" + "2" * 40, "0x" + "3" * 40]
    default_path = [decode_hex(e) for e in default_path_hex]

    def make_request(token_id: str = None, status: str = None, path: List[str] = None):
        url = api_url + f"/{to_checksum_address(token_network_model.address)}/feedback"

        token_id = token_id or uuid4().hex
        status = status or "success"
        path = path or default_path_hex
        data = {"token": token_id, "status": status, "path": path}
        return requests.post(url, json=data)

    # Request with invalid UUID
    response = make_request(token_id="abc")
    assert response.status_code == 400
    assert response.json()["error_code"] == exceptions.InvalidRequest.error_code

    # Request with invalid status
    response = make_request(status="abc")
    assert response.status_code == 400
    assert response.json()["error_code"] == exceptions.InvalidRequest.error_code

    # Request with invalid path
    response = make_request(path="abc")  # type: ignore
    assert response.status_code == 400
    assert response.json()["error_code"] == exceptions.InvalidRequest.error_code

    # Test valid token, which is not stored in PFS DB
    token = FeedbackToken(token_network_address=token_network_model.address)

    response = make_request(token_id=token.id.hex)
    assert response.status_code == 400
    assert not db_has_feedback_for(database, token, default_path)

    # Test expired token
    old_token = FeedbackToken(
        creation_time=datetime.utcnow() - timedelta(hours=1),
        token_network_address=token_network_model.address,
    )
    database.prepare_feedback(old_token, default_path)

    response = make_request(token_id=old_token.id.hex)
    assert response.status_code == 400
    assert not db_has_feedback_for(database, token, default_path)

    # Test valid token
    token = FeedbackToken(token_network_address=token_network_model.address)
    database.prepare_feedback(token, default_path)

    response = make_request(token_id=token.id.hex)
    assert response.status_code == 200
    assert db_has_feedback_for(database, token, default_path)
