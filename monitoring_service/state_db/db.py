

class StateDB:
    def __init__(self):
        pass

    @property
    def monitor_requests(self) -> dict:
        raise NotImplementedError

    def setup_db(self, chain_id: int, monitoring_contract_address: str, monitor_address: str):
        """Initialize an empty database. Call this if `is_initialized()` returns False"""
        raise NotImplementedError

    def get_monitor_request(self, channel_id: int) -> dict:
        """Given channel_id, returns a monitor request if it exists. Otherwise returns None."""
        raise NotImplementedError

    def delete_monitor_request(self, channel_id: int) -> None:
        """Delete monitor request from the DB"""
        raise NotImplementedError

    def is_initialized(self) -> bool:
        """Return True if database is initialized"""
        raise NotImplementedError

    def store_monitor_request(self, monitor_request) -> None:
        raise NotImplementedError

    def chain_id(self) -> int:
        """Return ethereum chain id this database was created with."""
        raise NotImplementedError

    def server_address(self) -> str:
        """Return ethereum address of Monitoring Service that created this database."""
        raise NotImplementedError

    def monitoring_contract_address(self) -> str:
        """Return ethereum address of Monitoring smart contract."""
        raise NotImplementedError
