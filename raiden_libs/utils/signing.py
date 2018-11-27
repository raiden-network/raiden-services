import warnings
from typing import Any, Callable, Optional, Union

from coincurve import PrivateKey, PublicKey
from eth_utils import (
    decode_hex,
    is_0x_prefixed,
    keccak,
    remove_0x_prefix,
    to_bytes,
    to_checksum_address,
)
from web3.utils.abi import map_abi_data
from web3.utils.encoding import hex_encode_abi_type
from web3.utils.normalizers import abi_address_to_hex

from raiden_libs.exceptions import InvalidSignature
from raiden_libs.types import Address

sha3 = keccak
Hasher = Optional[Callable[[bytes], bytes]]


def eth_sign_sha3(data: bytes) -> bytes:
    """
    eth_sign/recover compatible hasher
    Prefixes data with "\x19Ethereum Signed Message:\n<len(data)>"
    """
    prefix = b'\x19Ethereum Signed Message:\n'
    if not data.startswith(prefix):
        data = prefix + b'%d%s' % (len(data), data)
    return sha3(data)


def pack(*args) -> bytes:
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


def keccak256(*args, hasher: Hasher = sha3) -> bytes:
    """
    Simulates Solidity's keccak256 packing. Integers can be passed as tuples where the second tuple
    element specifies the variable's size in bits, e.g.:
    keccak256((5, 32))
    would be equivalent to Solidity's
    keccak256(uint32(5))
    Default size is 256.
    """
    if hasher:
        return hasher(pack(*args))
    else:
        return pack(*args)


def public_key_to_address(public_key: Union[PublicKey, bytes]) -> Address:
    """ Converts a public key to an Ethereum address. """
    if isinstance(public_key, PublicKey):
        public_key = public_key.format(compressed=False)
    assert isinstance(public_key, bytes)
    return to_checksum_address(sha3(public_key[1:])[-20:])


def private_key_to_address(private_key: Union[str, bytes]) -> Address:
    """ Converts a private key to an Ethereum address. """
    if isinstance(private_key, str):
        private_key = to_bytes(hexstr=private_key)
    pk = PrivateKey(private_key)
    return public_key_to_address(pk.public_key)


def address_from_signature(data: bytes, signature: bytes, hasher: Hasher = sha3) -> Address:
    """Convert an EC signature into an ethereum address"""
    if not isinstance(signature, bytes) or len(signature) != 65:
        raise InvalidSignature('Invalid signature, must be 65 bytes')
    # Support Ethereum's EC v value of 27 and EIP 155 values of > 35.
    if signature[-1] >= 35:
        network_id = (signature[-1] - 35) // 2
        signature = signature[:-1] + bytes([signature[-1] - 35 - 2 * network_id])
    elif signature[-1] >= 27:
        signature = signature[:-1] + bytes([signature[-1] - 27])

    try:
        signer_pubkey = PublicKey.from_signature_and_message(signature, data, hasher=hasher)
        return public_key_to_address(signer_pubkey)
    except Exception as e:  # pylint: disable=broad-except
        # coincurve raises bare exception on verify error
        raise InvalidSignature('Invalid signature') from e


def sign(
        privkey: Union[str, bytes, PrivateKey],
        data: bytes,
        v: int = 27,
        hasher: Hasher = sha3,
) -> bytes:
    if isinstance(privkey, str):
        privkey = to_bytes(hexstr=privkey)
    if isinstance(privkey, bytes):
        privkey = PrivateKey(privkey)
    sig = privkey.sign_recoverable(data, hasher=hasher)
    return sig[:-1] + bytes([sig[-1] + v])


def eth_sign(
        privkey: Union[str, bytes, PrivateKey],
        data: bytes,
        v: int = 27,
        hasher: Hasher = eth_sign_sha3,
) -> bytes:
    warnings.warn(
        'eth_sign from raiden-libs is deprecated. '
        'Function is now moved in the raiden client',
        DeprecationWarning,
    )
    return sign(privkey, data, v=v, hasher=hasher)


def eth_recover(data: bytes, signature: bytes, hasher: Hasher = eth_sign_sha3) -> Address:
    """ Recover an address (hex encoded) from a eth_sign data and signature """
    warnings.warn(
        'eth_recover from raiden-libs is deprecated. '
        'Function is now moved in the raiden client',
        DeprecationWarning,
    )
    return address_from_signature(data=data, signature=signature, hasher=hasher)


def eth_verify(data: Any, signature: bytes, hasher: Hasher = eth_sign_sha3) -> Address:
    """ Recover signature from data, which can be a list of values to be packed """
    return eth_recover(data=keccak256(data, hasher=hasher), signature=signature, hasher=None)


def pack_data(abi_types, values) -> bytes:
    """Normalize data and pack them into a byte array"""
    warnings.warn(
        'eth_recover from raiden-libs is deprecated. '
        'Function is now moved in the raiden client',
        DeprecationWarning,
    )
    if len(abi_types) != len(values):
        raise ValueError(
            "Length mismatch between provided abi types and values.  Got "
            "{0} types and {1} values.".format(len(abi_types), len(values)),
        )

    normalized_values = map_abi_data([abi_address_to_hex], abi_types, values)

    return decode_hex(''.join(
        remove_0x_prefix(hex_encode_abi_type(abi_type, value))
        for abi_type, value
        in zip(abi_types, normalized_values)
    ))
