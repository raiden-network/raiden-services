from coincurve import PrivateKey, PublicKey
from eth_utils import keccak

from raiden.utils.typing import Address
from raiden_contracts.utils.type_aliases import PrivateKey as PrivateKeyType


def camel_to_snake(input_str: str) -> str:
    return "".join(["_" + c.lower() if c.isupper() else c for c in input_str]).lstrip("_")


def public_key_to_address(public_key: PublicKey) -> Address:
    """ Converts a public key to an Ethereum address. """
    key_bytes = public_key.format(compressed=False)
    return Address(keccak(key_bytes[1:])[-20:])


def private_key_to_address(private_key: PrivateKeyType) -> Address:
    """ Converts a private key to an Ethereum address. """
    privkey = PrivateKey(private_key)
    return public_key_to_address(privkey.public_key)
