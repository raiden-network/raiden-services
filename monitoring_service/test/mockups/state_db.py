from monitoring_service.state_db.db import StateDB


class StateDBMock(StateDB):
    def __init__(self):
        super().__init__()
        self._balance_proofs = {}
        self._is_initialized = False

    @property
    def balance_proofs(self) -> dict:
        return self._balance_proofs

    def setup_db(self, network_id: int, contract_address: str, receiver: str):
        self._is_initialized = True

    def get_balance_proof(self, channel_id: int) -> dict:
        return self._balance_proofs.get(channel_id, None)

    def delete_balance_proof(self, channel_id: int) -> None:
        try:
            del self._balance_proofs[channel_id]
        except KeyError:
            pass

    def is_initialized(self) -> bool:
        return self._is_initialized

    def store_balance_proof(self, balance_proof) -> None:
        self._balance_proofs[balance_proof['channel_id']] = balance_proof
