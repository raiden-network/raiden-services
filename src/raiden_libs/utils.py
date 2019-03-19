from typing import Union

from coincurve import PrivateKey, PublicKey
from eth_utils import keccak, to_bytes, to_checksum_address

from raiden.constants import UINT256_MAX
from raiden_libs.types import Address, ChannelIdentifier, T_ChannelIdentifier


def is_channel_identifier(channel_identifier: ChannelIdentifier) -> bool:
    assert isinstance(channel_identifier, T_ChannelIdentifier)
    return 0 < channel_identifier <= UINT256_MAX


def public_key_to_address(public_key: Union[PublicKey, bytes]) -> Address:
    """ Converts a public key to an Ethereum address. """
    if isinstance(public_key, PublicKey):
        public_key = public_key.format(compressed=False)
    assert isinstance(public_key, bytes)
    return to_checksum_address(keccak(public_key[1:])[-20:])


def private_key_to_address(private_key: Union[str, bytes]) -> Address:
    """ Converts a private key to an Ethereum address. """
    if isinstance(private_key, str):
        private_key = to_bytes(hexstr=private_key)

    assert isinstance(private_key, bytes)
    pk = PrivateKey(private_key)
    return public_key_to_address(pk.public_key)
