from typing import Union

from coincurve import PrivateKey, PublicKey
from eth_utils import keccak, to_bytes

from raiden.utils.typing import Address


def public_key_to_address(public_key: PublicKey) -> Address:
    """ Converts a public key to an Ethereum address. """
    key_bytes = public_key.format(compressed=False)
    return Address(keccak(key_bytes[1:])[-20:])


def private_key_to_address(private_key: Union[str, bytes]) -> Address:
    """ Converts a private key to an Ethereum address. """
    if isinstance(private_key, str):
        private_key = to_bytes(hexstr=private_key)

    assert isinstance(private_key, bytes)
    privkey = PrivateKey(private_key)
    return public_key_to_address(privkey.public_key)
