import collections
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Type, TypeVar, cast
from uuid import UUID

import marshmallow
import pkg_resources
import structlog
from eth_utils import decode_hex, is_checksum_address, is_same_address, to_checksum_address
from flask import Flask, Response, request
from flask_restful import Api, Resource
from gevent.pywsgi import WSGIServer
from marshmallow import fields, validate
from marshmallow_dataclass import add_schema
from networkx.exception import NetworkXNoPath, NodeNotFound
from web3 import Web3

import pathfinding_service.exceptions as exceptions
from pathfinding_service.config import (
    API_PATH,
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DEFAULT_MAX_PATHS,
    MAX_AGE_OF_IOU_REQUESTS,
    MAX_PATHS_PER_REQUEST,
    MIN_IOU_EXPIRY,
    UDC_SECURITY_MARGIN_FACTOR,
)
from pathfinding_service.model import IOU
from pathfinding_service.model.feedback import FeedbackToken, RouteFeedback
from pathfinding_service.model.token_network import TokenNetwork
from pathfinding_service.service import PathfindingService
from raiden.exceptions import InvalidSignature
from raiden.utils.signer import recover
from raiden.utils.typing import Address, Signature, TokenAmount, TokenNetworkAddress
from raiden_libs.marshmallow import ChecksumAddress, HexedBytes

log = structlog.get_logger(__name__)
T = TypeVar("T")
# list stores max 200 last requests
last_requests: collections.deque = collections.deque([], maxlen=200)


class ApiWithErrorHandler(Api):
    def handle_error(self, e: Exception) -> Response:
        if isinstance(e, exceptions.ApiException):
            log.debug(
                "Error while handling request", error=e, details=e.error_details, message=e.msg
            )
            return self.make_response(
                {"errors": e.msg, "error_code": e.error_code, "error_details": e.error_details},
                e.http_code,
            )
        return super().handle_error(e)


class PathfinderResource(Resource):
    def __init__(self, pathfinding_service: PathfindingService, service_api: "ServiceApi"):
        self.pathfinding_service = pathfinding_service
        self.service_api = service_api

    def _validate_token_network_argument(self, token_network_address: str) -> TokenNetwork:
        if not is_checksum_address(token_network_address):
            raise exceptions.InvalidTokenNetwork(
                msg="The token network needs to be given as a checksummed address",
                token_network=token_network_address,
            )

        token_network = self.pathfinding_service.get_token_network(
            TokenNetworkAddress(decode_hex(token_network_address))
        )
        if token_network is None:
            raise exceptions.UnsupportedTokenNetwork(token_network=token_network_address)
        return token_network

    @staticmethod
    def _parse_post(req_class: T) -> T:
        json = request.get_json()
        if not json:
            raise exceptions.ApiException("JSON payload expected")
        req, errors = req_class.Schema().load(json)  # type: ignore
        if errors:
            raise exceptions.InvalidRequest(**errors)
        return req


@add_schema
@dataclass
class PathRequest:
    """A HTTP request to PathsResource"""

    from_: Address = field(
        metadata=dict(marshmallow_field=ChecksumAddress(required=True, load_from="from"))
    )
    to: Address = field(metadata=dict(marshmallow_field=ChecksumAddress(required=True)))
    value: TokenAmount = field(metadata=dict(validate=marshmallow.validate.Range(min=1)))
    max_paths: int = field(
        default=DEFAULT_MAX_PATHS,
        metadata=dict(validate=marshmallow.validate.Range(min=1, max=MAX_PATHS_PER_REQUEST)),
    )
    iou: Optional[IOU] = None
    diversity_penalty: Optional[float] = None
    fee_penalty: Optional[float] = None
    Schema: ClassVar[Type[marshmallow.Schema]]


class PathsResource(PathfinderResource):
    def __init__(self, debug_mode: bool, **kwargs: Any):
        super().__init__(**kwargs)
        self.debug_mode = debug_mode

    def post(self, token_network_address: str) -> Tuple[dict, int]:
        token_network = self._validate_token_network_argument(token_network_address)
        path_req = self._parse_post(PathRequest)
        process_payment(path_req.iou, self.pathfinding_service, self.service_api.service_fee)

        # only add optional args if not None, so we can use defaults
        optional_args = {}
        for arg in ["diversity_penalty", "fee_penalty"]:
            value = getattr(path_req, arg)
            if value is not None:
                optional_args[arg] = value
        try:
            paths = token_network.get_paths(
                source=path_req.from_,
                target=path_req.to,
                value=path_req.value,
                max_paths=path_req.max_paths,
                **optional_args,
            )
        except (NetworkXNoPath, NodeNotFound):
            # this is for assertion via the scenario player
            if self.debug_mode:
                last_requests.append(
                    dict(
                        token_network_address=to_checksum_address(token_network_address),
                        source=to_checksum_address(path_req.from_),
                        target=to_checksum_address(path_req.to),
                        routes=[],
                    )
                )
            raise exceptions.NoRouteFound(
                from_=to_checksum_address(path_req.from_), to=to_checksum_address(path_req.to)
            )

        # this is for assertion via the scenario player
        if self.debug_mode:
            last_requests.append(
                dict(
                    token_network_address=to_checksum_address(token_network_address),
                    source=to_checksum_address(path_req.from_),
                    target=to_checksum_address(path_req.to),
                    routes=paths,
                )
            )

        # Create a feedback token and store it to the DB
        feedback_token = create_and_store_feedback_token(
            pathfinding_service=self.pathfinding_service,
            token_network_address=token_network.address,
        )

        return {"result": {"paths": paths, "feedback_token": feedback_token.id.hex}}, 200


def create_and_store_feedback_token(
    pathfinding_service: PathfindingService, token_network_address: TokenNetworkAddress
) -> FeedbackToken:
    feedback_token = FeedbackToken(token_network_address=token_network_address)
    pathfinding_service.database.insert_feedback_token(feedback_token)

    return feedback_token


def process_payment(
    iou: Optional[IOU], pathfinding_service: PathfindingService, service_fee: TokenAmount
) -> None:
    if service_fee == 0:
        return
    if iou is None:
        raise exceptions.MissingIOU

    # Basic IOU validity checks
    if not is_same_address(iou.receiver, pathfinding_service.address):
        raise exceptions.WrongIOURecipient(expected=pathfinding_service.address)
    if not iou.is_signature_valid():
        raise exceptions.InvalidSignature

    # Compare with known IOU
    active_iou = pathfinding_service.database.get_iou(sender=iou.sender, claimed=False)
    if active_iou:
        if active_iou.expiration_block != iou.expiration_block:
            raise exceptions.UseThisIOU(iou=active_iou)

        expected_amount = active_iou.amount + service_fee
    else:
        claimed_iou = pathfinding_service.database.get_iou(
            sender=iou.sender, expiration_block=iou.expiration_block, claimed=True
        )
        if claimed_iou:
            raise exceptions.IOUAlreadyClaimed

        min_expiry = pathfinding_service.web3.eth.blockNumber + MIN_IOU_EXPIRY
        if iou.expiration_block < min_expiry:
            raise exceptions.IOUExpiredTooEarly(min_expiry=min_expiry)
        expected_amount = service_fee
    if iou.amount < expected_amount:
        raise exceptions.InsufficientServicePayment(expected_amount=expected_amount)

    # Check client's deposit in UserDeposit contract
    udc = pathfinding_service.user_deposit_contract
    udc_balance = udc.functions.effectiveBalance(iou.sender).call()
    required_deposit = round(expected_amount * UDC_SECURITY_MARGIN_FACTOR)
    if udc_balance < required_deposit:
        raise exceptions.DepositTooLow(required_deposit=required_deposit)

    log.info(
        "Received service fee",
        sender=iou.sender,
        expected_amount=expected_amount,
        total_amount=iou.amount,
        added_amount=expected_amount - service_fee,
    )

    # Save latest IOU
    iou.claimed = False
    pathfinding_service.database.upsert_iou(iou)


@add_schema
@dataclass
class IOURequest:
    """A HTTP request to IOUResource"""

    sender: Address = field(metadata={"marshmallow_field": ChecksumAddress(required=True)})
    receiver: Address = field(metadata={"marshmallow_field": ChecksumAddress(required=True)})
    timestamp: datetime
    timestamp_str: str = field(metadata={"load_from": "timestamp"})
    signature: Signature = field(metadata={"marshmallow_field": HexedBytes()})
    Schema: ClassVar[Type[marshmallow.Schema]]

    def is_signature_valid(self) -> bool:
        packed_data = self.sender + self.receiver + Web3.toBytes(text=self.timestamp_str)
        try:
            recovered_address = recover(packed_data, self.signature)
        except InvalidSignature:
            return False
        return is_same_address(recovered_address, self.sender)


class IOUResource(PathfinderResource):
    def get(
        self, token_network_address: str  # pylint: disable=unused-argument
    ) -> Tuple[dict, int]:
        iou_request, errors = IOURequest.Schema().load(request.args)
        if errors:
            raise exceptions.InvalidRequest(**errors)
        if not iou_request.is_signature_valid():
            raise exceptions.InvalidSignature
        if iou_request.timestamp < datetime.utcnow() - MAX_AGE_OF_IOU_REQUESTS:
            raise exceptions.RequestOutdated

        last_iou = self.pathfinding_service.database.get_iou(
            sender=iou_request.sender, claimed=False
        )
        if last_iou:
            last_iou = IOU.Schema(strict=True, exclude=["claimed"]).dump(last_iou)[0]
            return {"last_iou": last_iou}, 200

        return {"last_iou": None}, 404


@add_schema
@dataclass
class FeedbackRequest:
    """A HTTP request to FeedbackResource"""

    token: UUID = field(metadata={"required": True})
    status: str = field(
        metadata={
            "marshmallow_field": fields.Str(
                validate=validate.OneOf(("success", "failure")), required=True
            )
        }
    )
    path: List[Address] = field(
        metadata={"marshmallow_field": fields.List(ChecksumAddress, many=True), "required": True}
    )
    Schema: ClassVar[Type[marshmallow.Schema]]


class FeedbackResource(PathfinderResource):
    def post(
        self, token_network_address: str  # pylint: disable=unused-argument
    ) -> Tuple[dict, int]:
        token_network = self._validate_token_network_argument(token_network_address)
        feedback_request = self._parse_post(FeedbackRequest)
        feedback_token = self.pathfinding_service.database.get_feedback_token(
            token_id=feedback_request.token, token_network_address=token_network.address
        )

        # The client doesn't need to know whether the feedback was accepted or not,
        # so in case the token is invalid we still return HTTP 200
        if not feedback_token:
            return {}, 200
        if not feedback_token.is_valid():
            return {}, 200

        log.info("Received feedback", feedback=feedback_request)
        token_network.feedback.append(
            RouteFeedback(
                status=feedback_request.status,
                received_time=datetime.utcnow(),
                path=feedback_request.path,
            )
        )

        return {}, 200


class InfoResource(PathfinderResource):
    version = pkg_resources.get_distribution("raiden-services").version

    def get(self) -> Tuple[dict, int]:
        settings = "PLACEHOLDER FOR PATHFINDER SETTINGS"
        operator = "PLACEHOLDER FOR PATHFINDER OPERATOR"
        message = "PLACEHOLDER FOR ADDITIONAL MESSAGE BY THE PFS"

        return (
            {
                "price_info": self.service_api.service_fee,
                "network_info": {
                    "chain_id": self.pathfinding_service.chain_id,
                    "registry_address": to_checksum_address(
                        self.pathfinding_service.registry_address
                    ),
                },
                "settings": settings,
                "version": self.version,
                "operator": operator,
                "message": message,
                "payment_address": to_checksum_address(self.pathfinding_service.address),
            },
            200,
        )


class DebugEndpoint(PathfinderResource):
    def get(  # pylint: disable=no-self-use
        self, token_network_address: str, source_address: str, target_address: str = None
    ) -> Tuple[dict, int]:
        request_count = 0
        responses = []
        for req in last_requests:
            log.debug("Last Requests Values:", req=req)
            matches_params = is_same_address(
                token_network_address, req["token_network_address"]
            ) and is_same_address(source_address, req["source"])
            if target_address is not None:
                matches_params = matches_params and is_same_address(target_address, req["target"])

            if matches_params:
                request_count += 1
                responses.append(
                    dict(source=req["source"], target=req["target"], routes=req["routes"])
                )

        return dict(request_count=request_count, responses=responses), 200


class DebugEndpointIOU(PathfinderResource):
    def get(self, source_address: Address) -> Tuple[dict, int]:
        iou = self.pathfinding_service.database.get_iou(source_address)
        if iou:
            return (
                dict(
                    sender=to_checksum_address(iou.sender),
                    amount=iou.amount,
                    expiration_block=iou.expiration_block,
                ),
                200,
            )
        return {}, 200


class ServiceApi:
    def __init__(
        self,
        pathfinding_service: PathfindingService,
        service_fee: TokenAmount = TokenAmount(0),
        debug_mode: bool = False,
    ) -> None:
        self.flask_app = Flask(__name__)
        self.api = ApiWithErrorHandler(self.flask_app)
        self.rest_server: Optional[WSGIServer] = None
        self.pathfinding_service = pathfinding_service
        self.service_fee = service_fee

        resources: List[Tuple[str, Resource, Dict, str]] = [
            (
                "/<token_network_address>/paths",
                PathsResource,
                dict(debug_mode=debug_mode),
                "paths",
            ),
            ("/<token_network_address>/payment/iou", IOUResource, {}, "payments"),
            ("/<token_network_address>/feedback", FeedbackResource, {}, "feedback"),
            ("/info", InfoResource, {}, "info"),
        ]

        if debug_mode:
            log.warning("The debug REST API is enabled. Don't do this on public nodes.")
            resources.extend(
                [
                    (
                        "/_debug/routes/<token_network_address>/<source_address>",
                        cast(Resource, DebugEndpoint),
                        {},
                        "debug1",
                    ),
                    (
                        "/_debug/routes/<token_network_address>/<source_address>/<target_address>",
                        DebugEndpoint,
                        {},
                        "debug2",
                    ),
                    ("/_debug/ious/<source_address>", DebugEndpointIOU, {}, "debug3"),
                ]
            )

        for endpoint_url, resource, kwargs, endpoint in resources:
            endpoint_url = API_PATH + endpoint_url
            kwargs.update({"pathfinding_service": pathfinding_service, "service_api": self})
            self.api.add_resource(
                resource, endpoint_url, resource_class_kwargs=kwargs, endpoint=endpoint
            )

    def run(self, host: str = DEFAULT_API_HOST, port: int = DEFAULT_API_PORT) -> None:
        self.rest_server = WSGIServer((host, port), self.flask_app)
        self.rest_server.start()

        log.info("Running endpoint", endpoint=f"{host}:{port}")

    def stop(self) -> None:
        if self.rest_server:
            self.rest_server.stop()
