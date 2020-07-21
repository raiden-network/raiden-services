from raiden.network.transport.matrix import AddressReachability
from raiden.utils.typing import Address, Dict


class SimpleReachabilityContainer:  # pylint: disable=too-few-public-methods
    def __init__(self, reachabilities: Dict[Address, AddressReachability]) -> None:
        self.reachabilities = reachabilities
        self._userid_to_presence: dict = {}

    def get_address_reachability(self, address: Address) -> AddressReachability:
        return self.reachabilities.get(address, AddressReachability.UNKNOWN)
