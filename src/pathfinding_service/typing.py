from typing import Union

from raiden.messages import PFSCapacityUpdate, PFSFeeUpdate

DeferableMessage = Union[PFSFeeUpdate, PFSCapacityUpdate]
