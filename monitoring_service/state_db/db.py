

class StateDB:
    def __init__(self):
        pass

    @property
    def balance_proofs(self) -> dict:
        raise NotImplementedError

    def setup_db(self, network_id: int, contract_address: str, receiver: str):
        """Initialize an empty database. Call this if `is_initialized()` returns False"""
        raise NotImplementedError

    def get_balance_proof(self, channel_id: int) -> dict:
        """Given channel_id, returns a balance proof if it exists. Otherwise returns None."""
        raise NotImplementedError

    def delete_balance_proof(self, channel_id: int) -> None:
        """Delete balance proof from the DB"""
        raise NotImplementedError

    def is_initialized(self) -> bool:
        """Return True if database is initialized"""
        raise NotImplementedError

    def store_balance_proof(self, balance_proof) -> None:
        raise NotImplementedError
