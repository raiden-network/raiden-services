from datetime import datetime
from typing import List, Optional, Tuple, cast

import pkg_resources
import structlog
from eth_utils import to_checksum_address
from flask import Flask
from flask_restful import Resource
from gevent.pywsgi import WSGIServer
from prometheus_client import make_wsgi_app
from werkzeug.exceptions import NotFound
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from monitoring_service import metrics
from monitoring_service.constants import API_PATH, DEFAULT_INFO_MESSAGE
from monitoring_service.service import MonitoringService
from raiden_libs.api import ApiWithErrorHandler

log = structlog.get_logger(__name__)


class MSResource(Resource):
    def __init__(self, monitoring_service: MonitoringService, api: "MSApi"):
        self.monitoring_service = monitoring_service
        self.service_token_address = (
            self.monitoring_service.context.user_deposit_contract.functions.token().call()
        )
        self.api = api


class InfoResource(MSResource):
    version = pkg_resources.get_distribution("raiden-services").version
    contracts_version = pkg_resources.get_distribution("raiden-contracts").version

    def get(self) -> Tuple[dict, int]:
        info = {
            "price_info": self.api.monitoring_service.context.min_reward,
            "network_info": {
                "chain_id": self.monitoring_service.chain_id,
                "token_network_registry_address": to_checksum_address(
                    self.monitoring_service.context.ms_state.blockchain_state.token_network_registry_address  # noqa
                ),
                "user_deposit_address": to_checksum_address(
                    self.monitoring_service.context.user_deposit_contract.address
                ),
                "service_token_address": to_checksum_address(self.service_token_address),
                "confirmed_block": {
                    "number": self.monitoring_service.context.ms_state.blockchain_state.latest_committed_block  # noqa
                },
            },
            "version": self.version,
            "contracts_version": self.contracts_version,
            "operator": self.api.operator,
            "message": self.api.info_message,
            "UTC": datetime.utcnow().isoformat(),
        }
        return info, 200


class InfoResource2(MSResource):
    version = pkg_resources.get_distribution("raiden-services").version
    contracts_version = pkg_resources.get_distribution("raiden-contracts").version

    def get(self) -> Tuple[dict, int]:
        info = {
            "price_info": str(self.api.monitoring_service.context.min_reward),
            "network_info": {
                "chain_id": self.monitoring_service.chain_id,
                "token_network_registry_address": to_checksum_address(
                    self.monitoring_service.context.ms_state.blockchain_state.token_network_registry_address  # noqa
                ),
                "user_deposit_address": to_checksum_address(
                    self.monitoring_service.context.user_deposit_contract.address
                ),
                "service_token_address": to_checksum_address(self.service_token_address),
                "confirmed_block": {
                    "number": str(
                        self.monitoring_service.context.ms_state.blockchain_state.latest_committed_block  # noqa
                    )
                },
            },
            "version": self.version,
            "contracts_version": self.contracts_version,
            "operator": self.api.operator,
            "message": self.api.info_message,
            "UTC": datetime.utcnow().isoformat(),
        }
        return info, 200


class MSApi:
    def __init__(
        self,
        monitoring_service: MonitoringService,
        operator: str,
        info_message: str = DEFAULT_INFO_MESSAGE,
    ) -> None:
        flask_app = Flask(__name__)
        self.api = ApiWithErrorHandler(flask_app)

        # Add the metrics prometheus app
        self.flask_app = DispatcherMiddleware(
            NotFound(),
            {
                "/metrics": make_wsgi_app(registry=metrics.REGISTRY),
                API_PATH: flask_app.wsgi_app,
            },
        )

        self.rest_server: Optional[WSGIServer] = None

        self.monitoring_service = monitoring_service
        self.operator = operator
        self.info_message = info_message

        resources: List[Tuple[str, Resource, str]] = [
            ("/v1/info", cast(Resource, InfoResource), "info"),
            ("/v2/info", cast(Resource, InfoResource2), "info2"),
        ]

        for endpoint_url, resource, endpoint in resources:
            self.api.add_resource(
                resource,
                endpoint_url,
                resource_class_kwargs={"monitoring_service": monitoring_service, "api": self},
                endpoint=endpoint,
            )

    def run(self, host: str, port: int) -> None:
        self.rest_server = WSGIServer((host, port), self.flask_app)
        self.rest_server.start()

        log.info("Running endpoint", endpoint=f"http://{host}:{port}")

    def stop(self) -> None:
        if self.rest_server:
            self.rest_server.stop()
