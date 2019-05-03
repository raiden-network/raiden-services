# pylint: disable=invalid-name
from typing import NewType

T_TransactionHash = str
TransactionHash = NewType("TransactionHash", T_TransactionHash)
