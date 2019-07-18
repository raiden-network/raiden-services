from typing import Union

from raiden.messages.path_finding_service import PFSCapacityUpdate, PFSFeeUpdate

DeferableMessage = Union[PFSFeeUpdate, PFSCapacityUpdate]
