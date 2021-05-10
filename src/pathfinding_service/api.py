import collections
from dataclasses import dataclass, field
from datetime import MINYEAR, datetime
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Type, TypeVar, Union, cast
from uuid import UUID

import marshmallow
import pkg_resources
import structlog
from eth_utils import (
    is_checksum_address,
    is_same_address,
    to_canonical_address,
    to_checksum_address,
)
from flask import Flask, Response, request
from flask_restful import Resource
from gevent.pywsgi import WSGIServer
from marshmallow import fields
from marshmallow_dataclass import add_schema
from prometheus_client import make_wsgi_app
from web3 import Web3
from werkzeug.exceptions import NotFound
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from pathfinding_service import exceptions, metrics
from pathfinding_service.constants import (
    API_PATH,
    CACHE_TIMEOUT_SUGGEST_PARTNER,
    DEFAULT_INFO_MESSAGE,
    DEFAULT_MAX_PATHS,
    MAX_AGE_OF_IOU_REQUESTS,
    MAX_PATHS_PER_REQUEST,
    MIN_IOU_EXPIRY,
)
from pathfinding_service.model import IOU
from pathfinding_service.model.feedback import FeedbackToken
from pathfinding_service.model.token_network import Path, TokenNetwork
from pathfinding_service.service import PathfindingService
from raiden.exceptions import InvalidSignature
from raiden.network.transport.matrix.utils import UserPresence
from raiden.utils.signer import recover
from raiden.utils.typing import (
    Address,
    BlockNumber,
    PaymentAmount,
    PeerCapabilities,
    Signature,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_libs.api import ApiWithErrorHandler
from raiden_libs.blockchain import get_pessimistic_udc_balance
from raiden_libs.constants import UDC_SECURITY_MARGIN_FACTOR_PFS
from raiden_libs.exceptions import ApiException
from raiden_libs.marshmallow import ChecksumAddress, HexedBytes

log = structlog.get_logger(__name__)
T = TypeVar("T")
# list stores max 200 last requests
last_failed_requests: collections.deque = collections.deque([], maxlen=200)


class PathfinderResource(Resource):
    def __init__(self, pathfinding_service: PathfindingService, api: "PFSApi"):
        self.pathfinding_service = pathfinding_service
        self.api = api

    def _validate_token_network_argument(self, token_network_address: str) -> TokenNetwork:
        if not is_checksum_address(token_network_address):
            raise exceptions.InvalidTokenNetwork(
                msg="The token network needs to be given as a checksummed address",
                token_network=token_network_address,
            )

        token_network = self.pathfinding_service.get_token_network(
            TokenNetworkAddress(to_canonical_address(token_network_address))
        )
        if token_network is None:
            raise exceptions.UnsupportedTokenNetwork(token_network=token_network_address)
        return token_network

    @staticmethod
    def _parse_post(req_class: T) -> T:
        json = request.get_json()
        if not json:
            raise ApiException("JSON payload expected")
        try:
            return req_class.Schema().load(json)  # type: ignore
        except marshmallow.ValidationError as ex:
            raise exceptions.InvalidRequest(**ex.normalized_messages())


@add_schema
@dataclass
class PathRequest:
    """A HTTP request to PathsResource"""

    # pylint: disable=too-many-instance-attributes
    from_: Address = field(
        metadata=dict(marshmallow_field=ChecksumAddress(required=True, data_key="from"))
    )
    to: Address = field(metadata=dict(marshmallow_field=ChecksumAddress(required=True)))
    value: PaymentAmount = field(metadata=dict(validate=marshmallow.validate.Range(min=1)))
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
        process_payment(
            iou=path_req.iou,
            pathfinding_service=self.pathfinding_service,
            service_fee=self.api.service_fee,
            one_to_n_address=self.api.one_to_n_address,
        )

        # check for common error cases to provide clear error messages
        error = token_network.check_path_request_errors(
            source=path_req.from_,
            target=path_req.to,
            value=path_req.value,
            reachability_state=self.pathfinding_service.matrix_listener.user_manager,
        )

        if error:
            # this is for assertion via the scenario player
            if self.debug_mode:
                last_failed_requests.append(
                    dict(
                        token_network_address=to_checksum_address(token_network_address),
                        source=to_checksum_address(path_req.from_),
                        target=to_checksum_address(path_req.to),
                        routes=[],
                    )
                )

            # There is no synchronization on the block number updates and the
            # query performed above, so this may be higher than the original
            # value.
            approximate_error_block = (
                self.pathfinding_service.blockchain_state.latest_committed_block
            )
            msg = (
                f"{error}. Approximate block at the time of the request {approximate_error_block}"
            )
            raise exceptions.NoRouteFound(
                from_=to_checksum_address(path_req.from_),
                to=to_checksum_address(path_req.to),
                value=path_req.value,
                msg=msg,
            )

        # only add optional args if not None, so we can use defaults
        optional_args = {}
        for arg in ["diversity_penalty", "fee_penalty"]:
            value = getattr(path_req, arg)
            if value is not None:
                optional_args[arg] = value

        paths = token_network.get_paths(
            source=path_req.from_,
            target=path_req.to,
            value=path_req.value,
            reachability_state=self.pathfinding_service.matrix_listener.user_manager,
            max_paths=path_req.max_paths,
            **optional_args,
        )
        # this is for assertion via the scenario player
        if len(paths) == 0:
            if self.debug_mode:
                last_failed_requests.append(
                    dict(
                        token_network_address=to_checksum_address(token_network_address),
                        source=to_checksum_address(path_req.from_),
                        target=to_checksum_address(path_req.to),
                        routes=[],
                    )
                )
            raise exceptions.NoRouteFound(
                from_=to_checksum_address(path_req.from_),
                to=to_checksum_address(path_req.to),
                value=path_req.value,
            )
        # Create a feedback token and store it to the DB
        feedback_token = create_and_store_feedback_tokens(
            pathfinding_service=self.pathfinding_service,
            token_network_address=token_network.address,
            routes=paths,
        )
        return (
            {"result": [p.to_dict() for p in paths], "feedback_token": feedback_token.uuid.hex},
            200,
        )


def create_and_store_feedback_tokens(
    pathfinding_service: PathfindingService,
    token_network_address: TokenNetworkAddress,
    routes: List[Path],
) -> FeedbackToken:
    feedback_token = FeedbackToken(token_network_address=token_network_address)

    # TODO: use executemany here
    for route in routes:
        pathfinding_service.database.prepare_feedback(
            token=feedback_token, route=route.nodes, estimated_fee=route.estimated_fee
        )

    return feedback_token


def process_payment(  # pylint: disable=too-many-branches
    iou: Optional[IOU],
    pathfinding_service: PathfindingService,
    service_fee: TokenAmount,
    one_to_n_address: Address,
) -> None:
    if service_fee == 0:
        return
    if iou is None:
        raise exceptions.MissingIOU

    log.debug(
        "Checking IOU",
        sender=to_checksum_address(iou.sender),
        total_amount=iou.amount,
        expiration_block=iou.expiration_block,
    )

    # Basic IOU validity checks
    if not is_same_address(iou.receiver, pathfinding_service.address):
        raise exceptions.WrongIOURecipient(expected=pathfinding_service.address)
    if iou.chain_id != pathfinding_service.chain_id:
        raise exceptions.UnsupportedChainID(expected=pathfinding_service.chain_id)
    if iou.one_to_n_address != one_to_n_address:
        raise exceptions.WrongOneToNAddress(expected=one_to_n_address, got=iou.one_to_n_address)
    if not iou.is_signature_valid():
        raise exceptions.InvalidSignature

    # Compare with known IOU
    active_iou = pathfinding_service.database.get_iou(sender=iou.sender, claimed=False)
    if active_iou:
        if active_iou.expiration_block != iou.expiration_block:
            raise exceptions.UseThisIOU(iou=active_iou.Schema().dump(active_iou))

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
        raise exceptions.InsufficientServicePayment(
            expected_amount=expected_amount, actual_amount=iou.amount
        )

    # Check client's deposit in UserDeposit contract
    udc = pathfinding_service.user_deposit_contract
    latest_block = pathfinding_service.web3.eth.blockNumber
    udc_balance = get_pessimistic_udc_balance(
        udc=udc,
        address=iou.sender,
        from_block=BlockNumber(latest_block - pathfinding_service.required_confirmations),
        to_block=latest_block,
    )
    required_deposit = round(expected_amount * UDC_SECURITY_MARGIN_FACTOR_PFS)
    if udc_balance < required_deposit:
        raise exceptions.DepositTooLow(
            required_deposit=required_deposit, seen_deposit=udc_balance, block_number=latest_block
        )

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
    timestamp: datetime = field(metadata={"marshmallow_field": fields.NaiveDateTime()})
    timestamp_str: str = field(metadata=dict(data_key="timestamp", load_only=True))
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
        try:
            iou_request = IOURequest.Schema().load(request.args)
        except marshmallow.ValidationError as ex:
            raise exceptions.InvalidRequest(**ex.normalized_messages())
        if not iou_request.is_signature_valid():
            raise exceptions.InvalidSignature
        if iou_request.timestamp < datetime.utcnow() - MAX_AGE_OF_IOU_REQUESTS:
            raise exceptions.RequestOutdated

        last_iou = self.pathfinding_service.database.get_iou(
            sender=iou_request.sender, claimed=False
        )
        if last_iou:
            last_iou = IOU.Schema(exclude=["claimed"]).dump(last_iou)
            return {"last_iou": last_iou}, 200

        return {"last_iou": None}, 404


@add_schema
@dataclass
class FeedbackRequest:
    """A HTTP request to FeedbackResource"""

    token: UUID = field(metadata={"required": True})
    success: bool = field(metadata={"required": True})
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
            token_id=feedback_request.token,
            token_network_address=token_network.address,
            route=feedback_request.path,
        )

        # The client doesn't need to know whether the feedback was accepted or not,
        # so in case the token is invalid we return HTTP 400 without further infos
        if not feedback_token or not feedback_token.is_valid():
            return {}, 400

        updated_rows = self.pathfinding_service.database.update_feedback(
            token=feedback_token, route=feedback_request.path, successful=feedback_request.success
        )

        if updated_rows > 0:
            log.info(
                "Received feedback",
                token_network_address=to_checksum_address(feedback_token.token_network_address),
                feedback_token=feedback_request.token,
                feedback_route=[to_checksum_address(addr) for addr in feedback_request.path],
                was_success=feedback_request.success,
            )

        return {}, 200


class InfoResource(PathfinderResource):
    version = pkg_resources.get_distribution("raiden-services").version
    contracts_version = pkg_resources.get_distribution("raiden-contracts").version

    def get(self) -> Tuple[dict, int]:
        info = {
            "price_info": self.api.service_fee,
            "network_info": {
                "chain_id": self.pathfinding_service.chain_id,
                "token_network_registry_address": to_checksum_address(
                    self.pathfinding_service.registry_address
                ),
                "user_deposit_address": to_checksum_address(
                    self.pathfinding_service.user_deposit_contract.address
                ),
                "service_token_address": to_checksum_address(
                    self.pathfinding_service.service_token_address
                ),
                "confirmed_block": {
                    "number": self.pathfinding_service.blockchain_state.latest_committed_block
                },
            },
            "version": self.version,
            "contracts_version": self.contracts_version,
            "operator": self.api.operator,
            "message": self.api.info_message,
            "payment_address": to_checksum_address(self.pathfinding_service.address),
            "UTC": datetime.utcnow().isoformat(),
            "matrix_server": self.api.pathfinding_service.matrix_listener.base_url,
        }
        return info, 200


class InfoResource2(PathfinderResource):
    version = pkg_resources.get_distribution("raiden-services").version
    contracts_version = pkg_resources.get_distribution("raiden-contracts").version

    def get(self) -> Tuple[dict, int]:
        info = {
            "price_info": str(self.api.service_fee),
            "network_info": {
                "chain_id": self.pathfinding_service.chain_id,
                "token_network_registry_address": to_checksum_address(
                    self.pathfinding_service.registry_address
                ),
                "user_deposit_address": to_checksum_address(
                    self.pathfinding_service.user_deposit_contract.address
                ),
                "service_token_address": to_checksum_address(
                    self.pathfinding_service.service_token_address
                ),
                "confirmed_block": {
                    "number": str(self.pathfinding_service.blockchain_state.latest_committed_block)
                },
            },
            "version": self.version,
            "contracts_version": self.contracts_version,
            "operator": self.api.operator,
            "message": self.api.info_message,
            "payment_address": to_checksum_address(self.pathfinding_service.address),
            "UTC": datetime.utcnow().isoformat(),
            "matrix_server": self.api.pathfinding_service.matrix_listener.base_url,
        }
        return info, 200


class AddressMetadataResource(PathfinderResource):
    def get(self, checksummed_address: str) -> Tuple[Dict[str, Union[str, PeerCapabilities]], int]:
        address = self._validate_address_argument(checksummed_address)
        user_manager = self.pathfinding_service.matrix_listener.user_manager
        user_ids = user_manager.get_userids_for_address(address)

        for user_id in user_ids:
            if user_manager.get_userid_presence(user_id) in [
                UserPresence.ONLINE,
                UserPresence.UNAVAILABLE,
            ]:
                capabilities = user_manager.get_address_capabilities(address)
                return {"user_id": user_id, "capabilities": capabilities}, 200

        raise exceptions.AddressNotOnline(address=checksummed_address)

    @staticmethod
    def _validate_address_argument(address: str) -> Address:

        if not is_checksum_address(address):
            raise exceptions.InvalidAddress(
                msg="The address needs to be a valid checksummed Ethereum address",
                address=address,
            )

        return to_canonical_address(address)


class SuggestPartnerResource(PathfinderResource):

    cache: Dict[str, Tuple[list, datetime]] = {}

    def get(self, token_network_address: str) -> Tuple[List[Dict[str, Any]], int]:
        token_network = self._validate_token_network_argument(token_network_address)
        # Check cache
        cache_key = token_network_address
        cache_entry, cache_timestamp = self.cache.get(cache_key, (None, datetime(MINYEAR, 1, 1)))
        if cache_timestamp > datetime.utcnow() - CACHE_TIMEOUT_SUGGEST_PARTNER:
            assert cache_entry is not None
            return cache_entry, 200

        # Get result and write to cache
        suggestions = token_network.suggest_partner(
            self.pathfinding_service.matrix_listener.user_manager
        )
        self.cache[cache_key] = (suggestions, datetime.utcnow())

        return suggestions, 200


class DebugPathResource(PathfinderResource):
    def get(  # pylint: disable=no-self-use
        self,
        token_network_address: str,
        source_address: str,
        target_address: Optional[str] = None,
    ) -> Tuple[dict, int]:
        request_count = 0
        responses = []
        for req in last_failed_requests:
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

        decoded_target_address: Optional[Address] = None
        if target_address:
            decoded_target_address = to_canonical_address(target_address)

        feedback_routes = self.pathfinding_service.database.get_feedback_routes(
            TokenNetworkAddress(to_canonical_address(token_network_address)),
            to_canonical_address(source_address),
            decoded_target_address,
        )

        # Group routes after request (each request shares the `token_id`)
        grouped_routes: Dict[str, List[Dict]] = collections.defaultdict(list)
        for route in feedback_routes:
            grouped_routes[route["token_id"]].append(route)

        for requests in grouped_routes.values():
            routes = [
                {"path": route["route"], "estimated_fee": route["estimated_fee"]}
                for route in requests
            ]

            responses.append(
                {
                    "source": requests[0]["source_address"],
                    "target": requests[0]["target_address"],
                    "routes": routes,
                }
            )

            request_count += 1

        return dict(request_count=request_count, responses=responses), 200


class DebugIOUResource(PathfinderResource):
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


class DebugStatsResource(PathfinderResource):
    def get(self) -> Tuple[dict, int]:
        num_calculated_routes = self.pathfinding_service.database.get_num_routes_feedback()
        num_feedback_received = self.pathfinding_service.database.get_num_routes_feedback(
            only_with_feedback=True
        )
        num_successful = self.pathfinding_service.database.get_num_routes_feedback(
            only_successful=True
        )
        user_manager = self.pathfinding_service.matrix_listener.user_manager
        num_online_nodes = len(
            [
                presence
                # pylint: disable=protected-access
                for presence in user_manager._userid_to_presence.values()
                if presence == UserPresence.ONLINE
            ]
        )

        return (
            {
                "total_calculated_routes": num_calculated_routes,
                "total_feedback_received": num_feedback_received,
                "total_successful_routes": num_successful,
                "online_nodes": num_online_nodes,
            },
            200,
        )


class PFSApi:
    # pylint: disable=too-many-instance-attributes
    # Nine is reasonable in this case.

    def __init__(
        self,
        pathfinding_service: PathfindingService,
        one_to_n_address: Address,
        operator: str,
        info_message: str = DEFAULT_INFO_MESSAGE,
        service_fee: TokenAmount = TokenAmount(0),
        debug_mode: bool = False,
    ) -> None:
        flask_app = Flask(__name__)

        self.flask_app = DispatcherMiddleware(
            NotFound(),
            {
                "/metrics": make_wsgi_app(registry=metrics.REGISTRY),
                API_PATH: flask_app.wsgi_app,
            },
        )

        self.api = ApiWithErrorHandler(flask_app)
        self.rest_server: Optional[WSGIServer] = None
        self.one_to_n_address = one_to_n_address
        self.pathfinding_service = pathfinding_service
        self.service_fee = service_fee
        self.operator = operator
        self.info_message = info_message

        # Enable cross origin requests
        @flask_app.after_request
        def after_request(response: Response) -> Response:  # pylint: disable=unused-variable
            response.headers.add("Access-Control-Allow-Origin", "*")
            response.headers.add("Access-Control-Allow-Headers", "Origin, Content-Type, Accept")
            response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            return response

        resources: List[Tuple[str, Resource, Dict, str]] = [
            (
                "/v1/<token_network_address>/paths",
                PathsResource,
                dict(debug_mode=debug_mode),
                "paths",
            ),
            ("/v1/<token_network_address>/payment/iou", IOUResource, {}, "payments"),
            ("/v1/<token_network_address>/feedback", FeedbackResource, {}, "feedback"),
            (
                "/v1/<token_network_address>/suggest_partner",
                SuggestPartnerResource,
                {},
                "suggest_partner",
            ),
            ("/v1/info", InfoResource, {}, "info"),
            ("/v2/info", InfoResource2, {}, "info2"),
            (
                "/v1/address/<checksummed_address>/metadata",
                AddressMetadataResource,
                {},
                "address_metadata",
            ),
        ]

        if debug_mode:
            log.warning("The debug REST API is enabled. Don't do this on public nodes.")
            resources.extend(
                [
                    (
                        "/v1/_debug/routes/<token_network_address>/<source_address>",
                        cast(Resource, DebugPathResource),
                        {},
                        "debug1",
                    ),
                    (
                        "/v1/_debug/routes/<token_network_address>/<source_address>/<target_address>",  # noqa
                        DebugPathResource,
                        {},
                        "debug2",
                    ),
                    ("/v1/_debug/ious/<source_address>", DebugIOUResource, {}, "debug3"),
                    ("/v1/_debug/stats", DebugStatsResource, {}, "debug4"),
                ]
            )

        for endpoint_url, resource, kwargs, endpoint in resources:
            kwargs.update({"pathfinding_service": pathfinding_service, "api": self})
            self.api.add_resource(
                resource, endpoint_url, resource_class_kwargs=kwargs, endpoint=endpoint
            )

    def run(self, host: str, port: int) -> None:
        self.rest_server = WSGIServer((host, port), self.flask_app)
        self.rest_server.start()

        log.info("Running endpoint", endpoint=f"http://{host}:{port}")

    def stop(self) -> None:
        if self.rest_server:
            self.rest_server.stop()
