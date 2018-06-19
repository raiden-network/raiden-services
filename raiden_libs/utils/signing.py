# -*- coding: utf-8 -*-
from typing import Union, Any
from sha3 import keccak_256

from coincurve import PrivateKey, PublicKey
from web3.utils.abi import map_abi_data
from web3.utils.normalizers import abi_ens_resolver
from web3.utils.encoding import hex_encode_abi_type
from eth_utils import (
    to_checksum_address,
    encode_hex,
    decode_hex,
    keccak,
    remove_0x_prefix,
    is_0x_prefixed,
)

from raiden_libs.types import Address


def pack(*args) -> bytes:
    """
    Simulates Solidity's keccak256 packing. Integers can be passed as tuples where the second tuple
    element specifies the variable's size in bits, e.g.:
    keccak256((5, 32))
    would be equivalent to Solidity's
    keccak256(uint32(5))
    Default size is 256.
    """
    def format_int(value, size):
        assert isinstance(value, int)
        assert isinstance(size, int)
        if value >= 0:
            return decode_hex('{:x}'.format(value).zfill(size // 4))
        else:
            return decode_hex('{:x}'.format((1 << size) + value))

    msg = b''
    for arg in args:
        assert arg is not None
        if isinstance(arg, bytes):
            msg += arg
        elif isinstance(arg, str):
            if is_0x_prefixed(arg):
                msg += decode_hex(arg)
            else:
                msg += arg.encode()
        elif isinstance(arg, bool):
            msg += format_int(int(arg), 8)
        elif isinstance(arg, int):
            msg += format_int(arg, 256)
        elif isinstance(arg, tuple):
            msg += format_int(arg[0], arg[1])
        else:
            raise ValueError('Unsupported type: {}.'.format(type(arg)))

    return msg


def keccak256(*args) -> bytes:
    return keccak(pack(*args))


def sign(privkey: str, msg: bytes, v=0) -> bytes:
    assert isinstance(msg, bytes)
    assert isinstance(privkey, str)

    pk = PrivateKey.from_hex(remove_0x_prefix(privkey))
    assert len(msg) == 32

    sig = pk.sign_recoverable(msg, hasher=None)
    assert len(sig) == 65

    sig = sig[:-1] + bytes([sig[-1] + v])

    return sig


def sign_data(privkey: str, msg: bytes, v=27):
    pk = PrivateKey.from_hex(remove_0x_prefix(privkey))
    sha3 = lambda x: keccak_256(x).digest()
    sig = pk.sign_recoverable(msg, hasher=sha3)
    return sig[:-1] + chr(sig[-1] + v).encode()


def public_key_to_address(public_key: Union[PublicKey, bytes]) -> Address:
    """ Converts a public key to an Ethereum address. """
    if isinstance(public_key, PublicKey):
        public_key = public_key.format(compressed=False)
    assert isinstance(public_key, bytes)
    return encode_hex(keccak(public_key[1:])[-20:])


def private_key_to_address(private_key: str) -> Address:
    """ Converts a private key to an Ethereum address. """
    return to_checksum_address(
        public_key_to_address(PrivateKey.from_hex(remove_0x_prefix(private_key)).public_key),
    )


def address_from_signature(sig: bytes, msg: bytes) -> Address:
    """Convert an EC signature into an ethereum address"""
    assert len(sig) == 65
    # Support Ethereum's EC v value of 27 and EIP 155 values of > 35.
    if sig[-1] >= 35:
        network_id = (sig[-1] - 35) // 2
        sig = sig[:-1] + bytes([sig[-1] - 35 - 2 * network_id])
    elif sig[-1] >= 27:
        sig = sig[:-1] + bytes([sig[-1] - 27])

    receiver_pubkey = PublicKey.from_signature_and_message(sig, msg, hasher=None)
    return public_key_to_address(receiver_pubkey)


def eth_verify(sig: bytes, msg: Any) -> Address:
    return address_from_signature(sig, keccak256(msg))


def pack_data(abi_types, values) -> bytes:
    """Normalize data and pack them into a byte array"""
    if len(abi_types) != len(values):
        raise ValueError(
            "Length mismatch between provided abi types and values.  Got "
            "{0} types and {1} values.".format(len(abi_types), len(values)),
        )

    normalized_values = map_abi_data([abi_ens_resolver(None)], abi_types, values)

    return decode_hex(''.join(
        remove_0x_prefix(hex_encode_abi_type(abi_type, value))
        for abi_type, value
        in zip(abi_types, normalized_values)
    ))
