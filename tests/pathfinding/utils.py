from datetime import datetime
from typing import Set, Union
from unittest import mock

from eth_utils import to_normalized_address

from raiden.network.transport.matrix import AddressReachability, UserPresence
from raiden.network.transport.matrix.utils import ReachabilityState, address_from_userid
from raiden.utils.typing import Address, Dict


def get_user_id_from_address(address: Union[str, bytes]):
    return f"@{to_normalized_address(address)}:homeserver.com"


class SimpleReachabilityContainer:  # pylint: disable=too-few-public-methods
    def __init__(self, reachabilities: Dict[Address, AddressReachability]) -> None:
        self.reachabilities = reachabilities
        self.times = {address: datetime.utcnow() for address in reachabilities}
        self._userid_to_presence: dict = mock.MagicMock()
        self._address_to_userids: dict = mock.MagicMock()
        self._address_to_userids.__getitem__ = lambda self, key: {get_user_id_from_address(key)}

    def get_address_reachability(self, address: Address) -> AddressReachability:
        return self.reachabilities.get(address, AddressReachability.UNKNOWN)

    def get_address_reachability_state(self, address: Address) -> ReachabilityState:
        return ReachabilityState(
            self.reachabilities.get(address, AddressReachability.UNKNOWN),
            self.times.get(address, datetime.utcnow()),
        )

    def get_userid_presence(self, user_id: str) -> UserPresence:
        """ Return the current presence state of ``user_id``. """
        address = address_from_userid(user_id)
        return (
            UserPresence.ONLINE
            if address is not None
            and self.get_address_reachability(address) == AddressReachability.REACHABLE
            else UserPresence.UNKNOWN
        )

    def get_userids_for_address(self, address: Address) -> Set[str]:
        """ Return all known user ids for the given ``address``. """
        return self._address_to_userids[address]
