from typing import NewType

T_Address = str
Address = NewType("Address", T_Address)

T_TokenNetworkAddress = str
TokenNetworkAddress = NewType("TokenNetworkAddress", T_TokenNetworkAddress)

T_TransactionHash = str
TransactionHash = NewType("TransactionHash", T_TransactionHash)
