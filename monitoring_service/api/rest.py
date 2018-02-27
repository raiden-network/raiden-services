from flask import Flask, request
from flask_restful import Api, Resource
from gevent.pywsgi import WSGIServer
import gevent
from monitoring_service.blockchain import BlockchainMonitor
from monitoring_service import MonitoringService

API_PATH = '/api/1'


class BalanceProofResource(Resource):
    def __init__(self, monitor=None):
        super().__init__()
        assert isinstance(monitor, MonitoringService)
        self.monitor = monitor

    def get(self):
        return list(self.monitor.balance_proofs.values())


class BlockchainEvents(Resource):
    def __init__(self, blockchain=None):
        super().__init__()
        assert isinstance(blockchain, BlockchainMonitor)
        self.blockchain = blockchain

    def put(self):
        json_data = request.get_json()
        self.blockchain.handle_event(json_data)


class ServiceApi:
    def __init__(self, monitor, blockchain):
        self.flask_app = Flask(__name__)
        self.api = Api(self.flask_app)
        self.api.add_resource(BlockchainEvents, API_PATH + "/events",
                              resource_class_kwargs={'blockchain': blockchain})
        self.api.add_resource(BalanceProofResource, API_PATH + "/balance_proofs",
                              resource_class_kwargs={'monitor': monitor})

    def run(self, host, port):
        self.rest_server = WSGIServer((host, port), self.flask_app)
        self.server_greenlet = gevent.spawn(self.rest_server.serve_forever)
