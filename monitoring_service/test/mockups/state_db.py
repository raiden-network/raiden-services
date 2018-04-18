from monitoring_service.state_db.db import StateDB


class StateDBMock(StateDB):
    def __init__(self):
        super().__init__()
        self._monitor_requests = {}
        self._is_initialized = False

    @property
    def monitor_requests(self) -> dict:
        return self._monitor_requests

    def setup_db(self, network_id: int, contract_address: str, receiver: str):
        self._is_initialized = True

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
        self._monitor_requests[monitor_request['channel_identifier']] = monitor_request
