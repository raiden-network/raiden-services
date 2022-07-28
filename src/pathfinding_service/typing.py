from typing import Set, Union

from raiden_common.messages.path_finding_service import PFSCapacityUpdate, PFSFeeUpdate
from raiden_common.network.transport.matrix import UserPresence
from raiden_common.network.transport.matrix.utils import AddressReachability
from raiden_common.utils.typing import Address, PeerCapabilities
from typing_extensions import Protocol

DeferableMessage = Union[PFSFeeUpdate, PFSCapacityUpdate]


class AddressReachabilityProtocol(Protocol):
    # pylint: disable=unused-argument,no-self-use,too-few-public-methods

    def get_address_reachability(self, address: Address) -> AddressReachability:
        ...

    def get_userid_presence(self, user_id: str) -> UserPresence:
        ...

    def get_userids_for_address(self, address: Address) -> Set[str]:
        ...

    def get_address_capabilities(self, address: Address) -> PeerCapabilities:
        ...
