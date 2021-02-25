from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pkg_resources
import pytest
import requests
from eth_utils import (
    decode_hex,
    encode_hex,
    to_canonical_address,
    to_checksum_address,
    to_normalized_address,
)

from pathfinding_service import exceptions
from pathfinding_service.api import DEFAULT_MAX_PATHS, PFSApi, last_failed_requests
from pathfinding_service.constants import DEFAULT_INFO_MESSAGE
from pathfinding_service.model import IOU, TokenNetwork
from pathfinding_service.model.feedback import FeedbackToken
from raiden.network.transport.matrix import AddressReachability
from raiden.tests.utils.factories import make_signer
from raiden.utils.signer import LocalSigner
from raiden.utils.typing import (
    Address,
    BlockNumber,
    Callable,
    ChainID,
    FeeAmount,
    List,
    Optional,
    Signature,
    TokenAmount,
)
from raiden_contracts.tests.utils import get_random_privkey
from raiden_contracts.utils.type_aliases import PrivateKey
from raiden_libs.utils import private_key_to_address
from tests.pathfinding.test_database import db_has_feedback_for
from tests.pathfinding.utils import get_user_id_from_address

ID_12 = 12
ID_123 = 123


#
# tests for /_debug endpoint
#
@pytest.mark.usefixtures("api_sut")
def test_get_paths_via_debug_endpoint_with_debug_disabled(
    api_url: str, addresses: List[Address], token_network_model: TokenNetwork
):
    token_network_address_hex = to_checksum_address(token_network_model.address)
    address_hex = to_checksum_address(addresses[0])
    url_debug = api_url + f"/v1/_debug/routes/{token_network_address_hex}/{address_hex}"

    # now there must be a debug endpoint for that specific route
    response_debug = requests.get(url_debug)
    assert response_debug.status_code == 404


@pytest.mark.usefixtures("api_sut_with_debug")
def test_get_paths_via_debug_endpoint_a(
    api_url: str, addresses: List[Address], token_network_model: TokenNetwork
):  # pylint: disable=too-many-locals
    # `last_failed_requests` is a module variable, so it might have entries
    # from tests that ran earlier.
    last_failed_requests.clear()
    hex_addrs = [to_checksum_address(addr) for addr in addresses]
    token_network_address = to_checksum_address(token_network_model.address)

    # Make two requests, so we can test the `request_count` as well
    for _ in range(2):
        response = requests.post(
            api_url + f"/v1/{token_network_address}/paths",
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
        assert paths == [
            {
                "path": [hex_addrs[0], hex_addrs[1], hex_addrs[2]],
                "estimated_fee": 0,
                "matrix_users": {
                    hex_addrs[0]: get_user_id_from_address(hex_addrs[0]),
                    hex_addrs[1]: get_user_id_from_address(hex_addrs[1]),
                    hex_addrs[2]: get_user_id_from_address(hex_addrs[2]),
                },
            }
        ]

    # now there must be a debug endpoint for that specific route
    url_debug = api_url + f"/v1/_debug/routes/{token_network_address}/{hex_addrs[0]}"
    response_debug = requests.get(url_debug)
    assert response_debug.status_code == 200
    request_count = response_debug.json()["request_count"]
    assert request_count == 2
    responses = response_debug.json()["responses"]
    assert responses == [
        {
            "source": hex_addrs[0],
            "target": hex_addrs[2],
            "routes": [{"path": [hex_addrs[0], hex_addrs[1], hex_addrs[2]], "estimated_fee": 0}],
        },
        {
            "source": hex_addrs[0],
            "target": hex_addrs[2],
            "routes": [{"path": [hex_addrs[0], hex_addrs[1], hex_addrs[2]], "estimated_fee": 0}],
        },
    ]

    # now there must be a debug endpoint for that specific route and that specific target
    url_debug_incl_requested_target = (
        api_url + f"/v1/_debug/routes/{token_network_address}/{hex_addrs[0]}/{hex_addrs[2]}"
    )
    response_debug_incl_target = requests.get(url_debug_incl_requested_target)
    assert response_debug_incl_target.status_code == 200
    request_count = response_debug_incl_target.json()["request_count"]
    assert request_count == 2
    responses = response_debug.json()["responses"]
    assert responses == [
        {
            "source": hex_addrs[0],
            "target": hex_addrs[2],
            "routes": [{"path": [hex_addrs[0], hex_addrs[1], hex_addrs[2]], "estimated_fee": 0}],
        },
        {
            "source": hex_addrs[0],
            "target": hex_addrs[2],
            "routes": [{"path": [hex_addrs[0], hex_addrs[1], hex_addrs[2]], "estimated_fee": 0}],
        },
    ]

    # when requesting info for a target that was no path requested for
    url_debug_incl_unrequested_target = (
        api_url + f"/v1/_debug/routes/{token_network_address}/{hex_addrs[0]}/{hex_addrs[3]}"
    )
    response_debug_incl_unrequested_target = requests.get(url_debug_incl_unrequested_target)
    assert response_debug_incl_unrequested_target.status_code == 200
    request_count = response_debug_incl_unrequested_target.json()["request_count"]
    assert request_count == 0
    responses = response_debug_incl_unrequested_target.json()["responses"]
    assert responses == []


@pytest.mark.usefixtures("api_sut_with_debug")
def test_get_paths_via_debug_endpoint_empty_routes(
    api_url: str, addresses: List[Address], token_network_model: TokenNetwork
):
    # `last_failed_requests` is a module variable, so it might have entries
    # from tests that ran earlier.
    last_failed_requests.clear()
    hex_addrs = [to_checksum_address(addr) for addr in addresses]
    token_network_address = to_checksum_address(token_network_model.address)

    response = requests.post(
        api_url + f"/v1/{token_network_address}/paths",
        json={
            "from": hex_addrs[0],
            "to": hex_addrs[5],
            "value": 10,
            "max_paths": DEFAULT_MAX_PATHS,
        },
    )
    assert response.status_code == 404

    # test that requests with no routes found are returned as well
    url_debug_incl_impossible_route = (
        api_url + f"/v1/_debug/routes/{token_network_address}/{hex_addrs[0]}/{hex_addrs[5]}"
    )
    response_debug_incl_impossible_route = requests.get(url_debug_incl_impossible_route)
    assert response_debug_incl_impossible_route.status_code == 200
    request_count = response_debug_incl_impossible_route.json()["request_count"]
    assert request_count == 1

    response = requests.post(
        api_url + f"/v1/{token_network_address}/paths",
        json={
            "from": hex_addrs[0],
            "to": hex_addrs[6],
            "value": 1e10,
            "max_paths": DEFAULT_MAX_PATHS,
        },
    )
    assert response.status_code == 404

    # test that requests with no routes found are returned as well
    # regression test for https://github.com/raiden-network/raiden/issues/5421
    url_debug_incl_impossible_route = (
        api_url + f"/v1/_debug/routes/{token_network_address}/{hex_addrs[0]}/{hex_addrs[6]}"
    )
    response_debug_incl_impossible_route = requests.get(url_debug_incl_impossible_route)
    assert response_debug_incl_impossible_route.status_code == 200
    request_count = response_debug_incl_impossible_route.json()["request_count"]
    assert request_count == 1


def test_get_ious_via_debug_endpoint(
    api_sut_with_debug: PFSApi, api_url: str, addresses: List[Address]
):
    hex_addrs = [to_checksum_address(addr) for addr in addresses]
    iou = IOU(
        sender=addresses[0],
        receiver=addresses[4],
        amount=TokenAmount(111),
        expiration_block=BlockNumber(7619644),
        signature=Signature(
            decode_hex("118a93e9fd0a3a1c3d6edbad194b5c9d95715c754881d80e23e985793b1e13de")
        ),
        claimed=False,
        chain_id=ChainID(61),
        one_to_n_address=api_sut_with_debug.one_to_n_address,
    )
    api_sut_with_debug.pathfinding_service.database.upsert_iou(iou)

    # now there must be an iou debug endpoint for a request of a sender in the database
    url_iou_debug = api_url + f"/v1/_debug/ious/{hex_addrs[0]}"
    response_debug = requests.get(url_iou_debug)
    assert response_debug.status_code == 200
    response_iou = response_debug.json()
    assert response_iou == {"sender": hex_addrs[0], "amount": 111, "expiration_block": 7619644}

    # but there is no iou debug endpoint for a request of a sender not in the database
    url_iou_debug = api_url + f"/v1/_debug/ious/{hex_addrs[1]}"
    response_debug = requests.get(url_iou_debug)
    assert response_debug.status_code == 200
    ious = response_debug.json()
    assert ious == {}


#
# tests for /paths endpoint
#
def test_get_paths_validation(
    api_sut: PFSApi,
    api_url: str,
    addresses: List[Address],
    token_network_model: TokenNetwork,
    make_iou: Callable,
):
    initiator_address = to_checksum_address(addresses[0])
    target_address = to_checksum_address(addresses[1])
    url = api_url + "/v1/" + to_checksum_address(token_network_model.address) + "/paths"
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
    iou = make_iou(
        PrivateKey(decode_hex(get_random_privkey())),
        api_sut.pathfinding_service.address,
        one_to_n_address=api_sut.one_to_n_address,
    )
    good_iou_dict = iou.Schema().dump(iou)

    # malformed iou
    bad_iou_dict = good_iou_dict.copy()
    del bad_iou_dict["amount"]
    response = request_path_with(iou=bad_iou_dict)
    assert response.json()["error_code"] == exceptions.InvalidRequest.error_code

    # malformed iou
    bad_iou_dict = {
        "amount": {"_hex": "0x64"},
        "chain_id": {"_hex": "0x05"},
        "expiration_block": {"_hex": "0x188cba"},
        "one_to_n_address": "0x0000000000000000000000000000000000000000",
        "receiver": "0x94DEe8e391410A9ebbA791B187df2d993212c849",
        "sender": "0x2046F7341f15D0211ca1EBeFb19d029c4Bc4c4e7",
        "signature": (
            "0x0c3066e6a954d660028695f96dfe88cabaf0bc8a385e51781ac4d21003d0b6cd7a8b2"
            "a1134115845655d1a509061f48459cd401565b5df7845c913ed329cd2351b"
        ),
    }
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
        response = requests.post(api_url + "/v1" + url)
        assert response.status_code == 400
        assert response.json()["error_code"] == exceptions.InvalidTokenNetwork.error_code

    url = api_url + "/v1/0x0000000000000000000000000000000000000000/paths"
    response = requests.post(url)
    assert response.status_code == 400
    assert response.json()["error_code"] == exceptions.UnsupportedTokenNetwork.error_code


@pytest.mark.usefixtures("api_sut")
def test_get_paths(api_url: str, addresses: List[Address], token_network_model: TokenNetwork):
    hex_addrs = [to_checksum_address(addr) for addr in addresses]
    url = api_url + "/v1/" + to_checksum_address(token_network_model.address) + "/paths"

    data = {"from": hex_addrs[0], "to": hex_addrs[2], "value": 10, "max_paths": DEFAULT_MAX_PATHS}
    response = requests.post(url, json=data)
    assert response.status_code == 200
    paths = response.json()["result"]
    assert len(paths) == 1
    assert paths == [
        {
            "path": [hex_addrs[0], hex_addrs[1], hex_addrs[2]],
            "matrix_users": {
                hex_addrs[0]: get_user_id_from_address(hex_addrs[0]),
                hex_addrs[1]: get_user_id_from_address(hex_addrs[1]),
                hex_addrs[2]: get_user_id_from_address(hex_addrs[2]),
            },
            "estimated_fee": 0,
        }
    ]

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


def test_payment_with_new_iou_rejected(  # pylint: disable=too-many-locals
    api_sut,
    api_url: str,
    addresses: List[Address],
    token_network_model: TokenNetwork,
    make_iou: Callable,
):
    """ Regression test for https://github.com/raiden-network/raiden-services/issues/624 """

    initiator_address = to_checksum_address(addresses[0])
    target_address = to_checksum_address(addresses[1])
    url = api_url + "/v1/" + to_checksum_address(token_network_model.address) + "/paths"
    default_params = {"from": initiator_address, "to": target_address, "value": 5, "max_paths": 3}

    def request_path_with(status_code=400, **kwargs):
        params = default_params.copy()
        params.update(kwargs)
        response = requests.post(url, json=params)
        assert response.status_code == status_code, response.json()
        return response

    # test with payment
    api_sut.service_fee = 100
    sender = PrivateKey(decode_hex(get_random_privkey()))
    iou = make_iou(
        sender,
        api_sut.pathfinding_service.address,
        one_to_n_address=api_sut.one_to_n_address,
        amount=100,
        expiration_block=1_234_567,
    )
    first_iou_dict = iou.Schema().dump(iou)
    second_iou = make_iou(
        sender,
        api_sut.pathfinding_service.address,
        one_to_n_address=api_sut.one_to_n_address,
        amount=200,
        expiration_block=1_234_568,
    )
    second_iou_dict = second_iou.Schema().dump(second_iou)

    response = request_path_with(status_code=200, iou=first_iou_dict)
    assert response.status_code == 200

    response = request_path_with(iou=second_iou_dict)
    assert response.json()["error_code"] == exceptions.UseThisIOU.error_code


#
# tests for /info endpoint
#
def test_get_info(api_url: str, api_sut, pathfinding_service_mock):
    api_sut.service_fee = 123
    api_sut.operator = "John Doe"
    url = api_url + "/v1/info"

    token_network_registry_address = to_checksum_address(pathfinding_service_mock.registry_address)
    user_deposit_address = to_checksum_address(
        pathfinding_service_mock.user_deposit_contract.address
    )
    service_token_address = pathfinding_service_mock.user_deposit_contract.functions.token().call()

    expected_response = {
        "price_info": 123,
        "network_info": {
            "chain_id": pathfinding_service_mock.chain_id,
            "token_network_registry_address": token_network_registry_address,
            "user_deposit_address": user_deposit_address,
            "service_token_address": service_token_address,
            "confirmed_block": {"number": 0},
        },
        "version": pkg_resources.require("raiden-services")[0].version,
        "contracts_version": pkg_resources.require("raiden-contracts")[0].version,
        "operator": "John Doe",
        "message": DEFAULT_INFO_MESSAGE,
        "payment_address": to_checksum_address(pathfinding_service_mock.address),
        "matrix_server": "https://matrix.server",
        "matrix_room_id": "!room-id:matrix.server",
    }
    response = requests.get(url)
    assert response.status_code == 200
    response_json = response.json()
    del response_json["UTC"]
    assert response_json == expected_response

    # Test with a custom info message
    api_sut.info_message = expected_response["message"] = "Other message"
    response = requests.get(url)
    assert response.status_code == 200
    response_json = response.json()
    del response_json["UTC"]
    assert response_json == expected_response


def test_get_info2(api_url: str, api_sut, pathfinding_service_mock):
    api_sut.service_fee = 123
    api_sut.operator = "John Doe"
    url = api_url + "/v2/info"

    token_network_registry_address = to_checksum_address(pathfinding_service_mock.registry_address)
    user_deposit_address = to_checksum_address(
        pathfinding_service_mock.user_deposit_contract.address
    )
    service_token_address = pathfinding_service_mock.user_deposit_contract.functions.token().call()

    expected_response = {
        "price_info": "123",
        "network_info": {
            "chain_id": pathfinding_service_mock.chain_id,
            "token_network_registry_address": token_network_registry_address,
            "user_deposit_address": user_deposit_address,
            "service_token_address": service_token_address,
            "confirmed_block": {"number": "0"},
        },
        "version": pkg_resources.require("raiden-services")[0].version,
        "contracts_version": pkg_resources.require("raiden-contracts")[0].version,
        "operator": "John Doe",
        "message": DEFAULT_INFO_MESSAGE,
        "payment_address": to_checksum_address(pathfinding_service_mock.address),
        "matrix_server": "https://matrix.server",
        "matrix_room_id": "!room-id:matrix.server",
    }
    response = requests.get(url)
    assert response.status_code == 200
    response_json = response.json()
    del response_json["UTC"]
    assert response_json == expected_response

    # Test with a custom info message
    api_sut.info_message = expected_response["message"] = "Other message"
    response = requests.get(url)
    assert response.status_code == 200
    response_json = response.json()
    del response_json["UTC"]
    assert response_json == expected_response


@pytest.mark.usefixtures("api_sut")
def test_get_user(api_url: str, api_sut: PFSApi):
    address = make_signer().address
    checksummed_address = to_checksum_address(address)
    url = f"{api_url}/v1/user/{checksummed_address}"
    response = requests.get(url)
    assert response.status_code == 404

    user_manager = api_sut.pathfinding_service.matrix_listener.user_manager
    user_manager.reachabilities[address] = AddressReachability.REACHABLE

    response = requests.get(url)
    assert response.status_code == 200
    assert response.json()["user_id"] == get_user_id_from_address(address)


#
# tests for /payment/iou endpoint
#
def test_get_iou(api_sut: PFSApi, api_url: str, token_network_model: TokenNetwork, make_iou):
    privkey = PrivateKey(decode_hex(get_random_privkey()))
    sender = private_key_to_address(privkey)
    url = api_url + f"/v1/{to_checksum_address(token_network_model.address)}/payment/iou"

    def make_params(timestamp: str):
        params = {
            "sender": to_checksum_address(sender),
            "receiver": to_checksum_address(api_sut.pathfinding_service.address),
            "timestamp": timestamp,
        }
        local_signer = LocalSigner(private_key=privkey)
        params["signature"] = encode_hex(
            local_signer.sign(
                to_canonical_address(params["sender"])
                + to_canonical_address(params["receiver"])
                + params["timestamp"].encode("utf8")
            )
        )
        return params

    # Request without IOU in database
    params = make_params(datetime.utcnow().isoformat())
    response = requests.get(url, params=params)
    assert response.status_code == 404, response.json()
    assert response.json() == {"last_iou": None}

    # Add IOU to database
    iou = make_iou(
        privkey, api_sut.pathfinding_service.address, one_to_n_address=api_sut.one_to_n_address
    )
    iou.claimed = False
    api_sut.pathfinding_service.database.upsert_iou(iou)

    # Is returned IOU the one save into the db?
    response = requests.get(url, params=params)
    assert response.status_code == 200, response.json()
    iou_dict = IOU.Schema(exclude=["claimed"]).dump(iou)
    assert response.json()["last_iou"] == iou_dict

    # Invalid signatures must fail
    params["signature"] = encode_hex((int(params["signature"], 16) + 1).to_bytes(65, "big"))
    response = requests.get(url, params=params)
    assert response.status_code == 400, response.json()
    assert response.json()["error_code"] == exceptions.InvalidSignature.error_code

    # Timestamp must no be too old to prevent replay attacks
    old_timestamp = datetime.utcnow() - timedelta(days=1)
    params = make_params(old_timestamp.isoformat())
    response = requests.get(url, params=params)
    assert response.status_code == 400, response.json()
    assert response.json()["error_code"] == exceptions.RequestOutdated.error_code

    # Timestamp with timezone info is invalid
    for timestamp in (datetime.now(tz=timezone.utc).isoformat(), "2019-11-07T12:52:25.079Z"):
        params = make_params(timestamp)
        response = requests.get(url, params=params)
        assert response.status_code == 400, response.json()
        assert response.json()["error_code"] == exceptions.InvalidRequest.error_code


#
# tests for /feedback endpoint
#
def test_feedback(api_sut: PFSApi, api_url: str, token_network_model: TokenNetwork):
    database = api_sut.pathfinding_service.database
    default_path_hex = ["0x" + "1" * 40, "0x" + "2" * 40, "0x" + "3" * 40]
    default_path = [to_canonical_address(e) for e in default_path_hex]
    estimated_fee = FeeAmount(0)

    def make_request(
        token_id: Optional[str] = None, success: bool = True, path: Optional[List[str]] = None
    ):
        url = api_url + f"/v1/{to_checksum_address(token_network_model.address)}/feedback"

        token_id = token_id or uuid4().hex
        path = path or default_path_hex
        data = {"token": token_id, "success": success, "path": path}
        return requests.post(url, json=data)

    # Request with invalid UUID
    response = make_request(token_id="abc")
    assert response.status_code == 400
    assert response.json()["error_code"] == exceptions.InvalidRequest.error_code

    # Request with invalid path
    response = make_request(path=["abc"])
    assert response.status_code == 400
    assert response.json()["error_code"] == exceptions.InvalidRequest.error_code

    # Test valid token, which is not stored in PFS DB
    token = FeedbackToken(token_network_address=token_network_model.address)

    response = make_request(token_id=token.uuid.hex)
    assert response.status_code == 400
    assert not db_has_feedback_for(database, token, default_path)

    # Test expired token
    old_token = FeedbackToken(
        creation_time=datetime.utcnow() - timedelta(hours=1),
        token_network_address=token_network_model.address,
    )
    database.prepare_feedback(old_token, default_path, estimated_fee)

    response = make_request(token_id=old_token.uuid.hex)
    assert response.status_code == 400
    assert not db_has_feedback_for(database, token, default_path)

    # Test valid token
    token = FeedbackToken(token_network_address=token_network_model.address)
    database.prepare_feedback(token, default_path, estimated_fee)

    response = make_request(token_id=token.uuid.hex)
    assert response.status_code == 200
    assert db_has_feedback_for(database, token, default_path)


def test_stats_endpoint(
    api_sut_with_debug: PFSApi, api_url: str, token_network_model: TokenNetwork
):
    database = api_sut_with_debug.pathfinding_service.database
    default_path = [Address(b"1" * 20), Address(b"2" * 20), Address(b"3" * 20)]
    feedback_token = FeedbackToken(token_network_model.address)
    estimated_fee = FeeAmount(0)

    def check_response(num_all: int, num_only_feedback: int, num_only_success: int) -> None:
        url = api_url + "/v1/_debug/stats"
        response = requests.get(url)

        assert response.status_code == 200

        data = response.json()
        assert data["total_calculated_routes"] == num_all
        assert data["total_feedback_received"] == num_only_feedback
        assert data["total_successful_routes"] == num_only_success

    database.prepare_feedback(feedback_token, default_path, estimated_fee)
    check_response(1, 0, 0)

    database.update_feedback(feedback_token, default_path, False)
    check_response(1, 1, 0)

    default_path2 = default_path[1:]
    feedback_token2 = FeedbackToken(token_network_model.address)

    database.prepare_feedback(feedback_token2, default_path2, estimated_fee)
    check_response(2, 1, 0)

    database.update_feedback(feedback_token2, default_path2, True)
    check_response(2, 2, 1)


@pytest.mark.usefixtures("api_sut")
def test_cors(api_url: str):
    headers = {
        "Origin": "http://example.com/",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "X-Requested-With",
    }

    response = requests.options(api_url, headers=headers)
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert response.headers["Access-Control-Allow-Headers"] == "Origin, Content-Type, Accept"


@pytest.mark.usefixtures("api_sut")
def test_suggest_partner_api(api_url: str, token_network_model: TokenNetwork):
    """Smoke test for partner suggestion REST endpoint

    The actual content is tested in ``test_graphs.test_suggest_partner``.
    """
    token_network_address_hex = to_checksum_address(token_network_model.address)
    url = api_url + f"/v1/{token_network_address_hex}/suggest_partner"
    response = requests.get(url)
    assert response.status_code == 200
