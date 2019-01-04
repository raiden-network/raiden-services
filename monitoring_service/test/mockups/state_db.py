from monitoring_service.state_db.db import StateDB


class StateDBMock(StateDB):
    def __init__(self):
        super().__init__()
        self._monitor_requests = {}
        self._is_initialized = False
        self._chain_id = None
        self._server_address = None
        self._contract_address = None

    @property
    def monitor_requests(self) -> dict:
        return {
            x.balance_proof.channel_identifier: x
            for x in self._monitor_requests.values()
        }

    def setup_db(self, network_id: int, contract_address: str, server_address: str):
        self._is_initialized = True
        self._chain_id = network_id
        self._contract_address = contract_address
        self._server_address = server_address

    def get_monitor_request(self, channel_id: int) -> dict:
        return self._monitor_requests.get(channel_id, None)

    def delete_monitor_request(self, channel_id: int) -> None:
        try:
            del self._monitor_requests[channel_id]
        except KeyError:
            pass

    def is_initialized(self) -> bool:
        return self._is_initialized

    def store_monitor_request(self, monitor_request) -> None:
        self._monitor_requests[
            monitor_request.balance_proof.channel_identifier
        ] = monitor_request

    def chain_id(self) -> int:
        return self._chain_id

    def server_address(self) -> str:
        return self._server_address

    def monitoring_contract_address(self) -> str:
        return self._contract_address
