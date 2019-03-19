from datetime import datetime
from typing import ClassVar, Dict, List, Optional, Tuple, Type

import gevent
import marshmallow
import pkg_resources
import structlog
from dataclasses import dataclass, field
from eth_utils import is_address, is_checksum_address, is_same_address
from flask import Flask, request
from flask_restful import Api, Resource, reqparse
from gevent import Greenlet
from gevent.pywsgi import WSGIServer
from marshmallow_dataclass import add_schema
from networkx.exception import NetworkXNoPath
from web3 import Web3

import pathfinding_service.exceptions as exceptions
from pathfinding_service import PathfindingService
from pathfinding_service.config import (
    API_PATH,
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DEFAULT_MAX_PATHS,
    MAX_AGE_OF_IOU_REQUESTS,
    MIN_IOU_EXPIRY,
)
from pathfinding_service.model import IOU
from raiden.utils.typing import Signature, TokenNetworkAddress
from raiden_libs.exceptions import InvalidSignature
from raiden_libs.marshmallow import HexedBytes
from raiden_libs.types import Address
from raiden_libs.utils import eth_recover

log = structlog.get_logger(__name__)


class ApiWithErrorHandler(Api):

    def handle_error(self, e):
        return self.make_response({
            'errors': e.msg,
            'error_code': e.error_code,
            'error_details': e.error_details,
        }, e.http_code)


class PathfinderResource(Resource):

    def __init__(self, pathfinding_service: PathfindingService):
        self.pathfinding_service = pathfinding_service

    def _validate_token_network_argument(
        self,
        token_network_address: str,
    ) -> Optional[Tuple[Dict, int]]:

        if not is_address(token_network_address):
            no_address_message = 'Invalid token network address: {}'
            return {'errors': no_address_message.format(token_network_address)}, 400

        if not is_checksum_address(token_network_address):
            address_error = 'Token network address not checksummed: {}'
            return {'errors': address_error.format(token_network_address)}, 400

        token_network = self.pathfinding_service.token_networks.get(
            Address(token_network_address),
        )
        if token_network is None:
            return {
                'errors': 'Unsupported token network: {}'.format(token_network_address),
            }, 400

        return None


class PathsResource(PathfinderResource):
    @staticmethod
    def _validate_args(args):
        required_args = ['from', 'to', 'value', 'max_paths']
        if not all(args[arg] is not None for arg in required_args):
            return {'errors': 'Required parameters: {}'.format(required_args)}, 400

        address_error = 'Invalid {} address: {}'
        if not is_address(args['from']):
            return {'errors': address_error.format('initiator', args['from'])}, 400
        if not is_address(args['to']):
            return {'errors': address_error.format('target', args['to'])}, 400

        address_error = '{} address not checksummed: {}'
        if not is_checksum_address(args['from']):
            return {'errors': address_error.format('Initiator', args['from'])}, 400
        if not is_checksum_address(args['to']):
            return {'errors': address_error.format('Target', args['to'])}, 400

        if args.value < 0:
            return {'errors': 'Payment value must be non-negative: {}'.format(args.value)}, 400

        if args.max_paths <= 0:
            return {'errors': 'Number of paths must be positive: {}'.format(args.max_paths)}, 400

        return None

    def post(self, token_network_address: str):
        token_network_error = self._validate_token_network_argument(token_network_address)
        if token_network_error is not None:
            return token_network_error

        parser = reqparse.RequestParser()
        parser.add_argument('from', type=str, help='Payment initiator address.')
        parser.add_argument('to', type=str, help='Payment target address.')
        parser.add_argument('value', type=int, help='Maximum payment value.')
        parser.add_argument(
            'max_paths',
            type=int,
            help='Number of paths requested.',
            default=DEFAULT_MAX_PATHS,
        )

        args = parser.parse_args()
        error = self._validate_args(args)
        if error is not None:
            return error

        json = request.get_json()
        if not json:
            raise exceptions.ApiException('JSON payload expected')
        process_payment(json.get('iou'), self.pathfinding_service)

        token_network = self.pathfinding_service.token_networks.get(
            Address(token_network_address),
        )
        # Existence is checked in _validate_token_network_argument
        assert token_network, 'Requested token network cannot be found'

        try:
            paths = token_network.get_paths(
                source=args['from'],
                target=args['to'],
                value=args.value,
                max_paths=args.max_paths,
            )
        except NetworkXNoPath:
            return {'errors': 'No suitable path found for transfer from {} to {}.'.format(
                args['from'], args['to'],
            )}, 400

        return {'result': paths}, 200


def process_payment(iou_dict: dict, pathfinding_service: PathfindingService):
    if pathfinding_service.service_fee == 0:
        return
    if iou_dict is None:
        raise exceptions.MissingIOU

    # Basic IOU validity checks
    iou, errors = IOU.Schema().load(iou_dict)
    if errors:
        raise exceptions.InvalidRequest(**errors)
    if iou.receiver != pathfinding_service.address:
        raise exceptions.WrongIOURecipient(expected=pathfinding_service.address)
    if not iou.is_signature_valid():
        raise exceptions.InvalidSignature

    # Compare with known IOU
    active_iou = pathfinding_service.database.get_iou(
        sender=iou.sender,
        claimed=False,
    )
    if active_iou:
        if active_iou.expiration_block != iou.expiration_block:
            raise exceptions.UseThisIOU(iou=active_iou)

        expected_amount = active_iou.amount + pathfinding_service.service_fee
    else:
        claimed_iou = pathfinding_service.database.get_iou(
            sender=iou.sender,
            expiration_block=iou.expiration_block,
            claimed=True,
        )
        if claimed_iou:
            raise exceptions.IOUAlreadyClaimed

        min_expiry = pathfinding_service.web3.eth.blockNumber + MIN_IOU_EXPIRY
        if iou.expiration_block < min_expiry:
            raise exceptions.IOUExpiredTooEarly(min_expiry=min_expiry)
        expected_amount = pathfinding_service.service_fee
    if iou.amount < expected_amount:
        raise exceptions.InsufficientServicePayment(expected_amount=expected_amount)

    # TODO: deposit large enough?

    # Save latest IOU
    iou.claimed = False
    pathfinding_service.database.upsert_iou(iou)


@add_schema
@dataclass
class IOURequest:
    """A HTTP request to IOUResource"""
    sender: Address
    receiver: Address
    timestamp: datetime
    timestamp_str: str = field(metadata={
        "marshmallow_field": marshmallow.fields.String(load_from='timestamp'),
    })
    signature: Signature = field(metadata={"marshmallow_field": HexedBytes()})
    Schema: ClassVar[Type[marshmallow.Schema]]

    def is_signature_valid(self):
        packed_data = (
            Web3.toBytes(hexstr=self.sender) +
            Web3.toBytes(hexstr=self.receiver) +
            Web3.toBytes(text=self.timestamp_str)
        )
        try:
            recovered_address = eth_recover(packed_data, self.signature)
        except InvalidSignature:
            return False
        return is_same_address(recovered_address, self.sender)


class IOUResource(PathfinderResource):

    def get(self, token_network_address: TokenNetworkAddress):
        iou_request, errors = IOURequest.Schema().load(request.args)
        if errors:
            raise exceptions.InvalidRequest(**errors)
        if not iou_request.is_signature_valid():
            raise exceptions.InvalidSignature
        if iou_request.timestamp < datetime.utcnow() - MAX_AGE_OF_IOU_REQUESTS:
            raise exceptions.RequestOutdated

        last_iou = self.pathfinding_service.database.get_iou(
            sender=iou_request.sender,
            claimed=False,
        )
        if last_iou:
            last_iou = IOU.Schema(strict=True, exclude=['claimed']).dump(last_iou)[0]
            return {
                'last_iou': last_iou,
            }, 200
        else:
            return {
                'last_iou': None,
            }, 404


class InfoResource(PathfinderResource):
    version = pkg_resources.get_distribution('raiden-services').version

    def get(self):
        price = 0
        settings = 'PLACEHOLDER FOR PATHFINDER SETTINGS'
        operator = 'PLACEHOLDER FOR PATHFINDER OPERATOR'
        message = 'PLACEHOLDER FOR ADDITIONAL MESSAGE BY THE PFS'

        return {
            'price_info': price,
            'network_info': {
                'chain_id': self.pathfinding_service.chain_id,
                'registry_address': self.pathfinding_service.registry_address,
            },
            'settings': settings,
            'version': self.version,
            'operator': operator,
            'message': message,
        }, 200


class ServiceApi:
    def __init__(self, pathfinding_service: PathfindingService):
        self.flask_app = Flask(__name__)
        self.api = ApiWithErrorHandler(self.flask_app)
        self.rest_server: WSGIServer = None
        self.server_greenlet: Greenlet = None
        self.pathfinding_service = pathfinding_service

        resources: List[Tuple[str, Resource, Dict]] = [
            ('/<token_network_address>/paths', PathsResource, {}),
            ('/<token_network_address>/payment/iou', IOUResource, {}),
            ('/info', InfoResource, {}),
        ]

        for endpoint_url, resource, kwargs in resources:
            endpoint_url = API_PATH + endpoint_url
            kwargs['pathfinding_service'] = pathfinding_service
            self.api.add_resource(resource, endpoint_url, resource_class_kwargs=kwargs)

    def run(self, host: str = DEFAULT_API_HOST, port: int = DEFAULT_API_PORT):
        self.rest_server = WSGIServer((host, port), self.flask_app)
        self.server_greenlet = gevent.spawn(self.rest_server.serve_forever)

        log.info('Running endpoint', endpoint=f'{host}:{port}')

    def stop(self):
        self.server_greenlet.kill()
