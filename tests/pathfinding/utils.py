from datetime import datetime

from raiden.network.transport.matrix import AddressReachability
from raiden.network.transport.matrix.utils import ReachabilityState
from raiden.utils.typing import Address, Dict


class SimpleReachabilityContainer:  # pylint: disable=too-few-public-methods
    def __init__(self, reachabilities: Dict[Address, AddressReachability]) -> None:
        self.reachabilities = reachabilities
        self.times = {address: datetime.utcnow() for address in reachabilities}
        self._userid_to_presence: dict = {}

    def get_address_reachability(self, address: Address) -> AddressReachability:
        return self.reachabilities.get(address, AddressReachability.UNKNOWN)

    def get_address_reachability_state(self, address: Address) -> ReachabilityState:
        return ReachabilityState(
            self.reachabilities.get(address, AddressReachability.UNKNOWN),
            self.times.get(address, datetime.utcnow()),
        )
