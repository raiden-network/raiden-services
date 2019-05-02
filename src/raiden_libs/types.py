# pylint: disable=invalid-name
from typing import NewType

T_Address = str
Address = NewType("Address", T_Address)

T_TransactionHash = str
TransactionHash = NewType("TransactionHash", T_TransactionHash)
