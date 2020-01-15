from typing import Union

from typing_extensions import Protocol

from raiden.messages.path_finding_service import PFSCapacityUpdate, PFSFeeUpdate
from raiden.network.transport.matrix.utils import AddressReachability
from raiden.utils.typing import Address

DeferableMessage = Union[PFSFeeUpdate, PFSCapacityUpdate]


class AddressReachabilityProtocol(Protocol):
    # pylint: disable=unused-argument,no-self-use,too-few-public-methods

    def get_address_reachability(self, address: Address) -> AddressReachability:
        ...
