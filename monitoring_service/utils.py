import functools
from eth_utils import (
    decode_hex,
    encode_hex,
    is_0x_prefixed,
    remove_0x_prefix,
    to_checksum_address,
    keccak,
)
from ethereum.abi import (
    decode_abi,
    normalize_name as normalize_abi_method_name,
    method_id as get_abi_method_id,
    encode_int,
    zpad
)
from coincurve import PrivateKey, PublicKey
from web3.utils.filters import construct_event_filter_params
from web3.utils.events import get_event_data


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


def pubkey_to_addr(pubkey) -> str:
    if isinstance(pubkey, PublicKey):
        pubkey = pubkey.format(compressed=False)
    assert isinstance(pubkey, bytes)
    return encode_hex(keccak256(pubkey[1:])[-20:])


def privkey_to_addr(privkey: str) -> str:
    return to_checksum_address(
        pubkey_to_addr(PrivateKey.from_hex(remove_0x_prefix(privkey)).public_key)
    )


def sign(privkey: str, msg: bytes, v=0) -> bytes:
    assert isinstance(msg, bytes)
    assert isinstance(privkey, str)

    pk = PrivateKey.from_hex(remove_0x_prefix(privkey))
    assert len(msg) == 32

    sig = pk.sign_recoverable(msg, hasher=None)
    assert len(sig) == 65

    sig = sig[:-1] + bytes([sig[-1] + v])

    return sig


def addr_from_sig(sig: bytes, msg: bytes):
    assert len(sig) == 65
    # Support Ethereum's EC v value of 27 and EIP 155 values of > 35.
    if sig[-1] >= 35:
        network_id = (sig[-1] - 35) // 2
        sig = sig[:-1] + bytes([sig[-1] - 35 - 2 * network_id])
    elif sig[-1] >= 27:
        sig = sig[:-1] + bytes([sig[-1] - 27])

    receiver_pubkey = PublicKey.from_signature_and_message(sig, msg, hasher=None)
    return pubkey_to_addr(receiver_pubkey)


def eth_verify(sig: bytes, msg: str) -> str:
    return addr_from_sig(sig, keccak256(msg))


def make_filter(web3, event_abi, filters={}, **filter_kwargs):
    assert event_abi != []
    log_data_extract_fn = functools.partial(get_event_data, event_abi)
    data_filter_set, filter_params = construct_event_filter_params(
        event_abi,
        argument_filters=filters,
        **filter_kwargs
    )

    event_filter = web3.eth.filter(filter_params)
    event_filter.log_entry_formatter = log_data_extract_fn
    event_filter.set_data_filters(data_filter_set)
    event_filter.filter_params = filter_params
    return event_filter


def decode_contract_call(contract_abi: list, call_data: str):
    call_data_bin = decode_hex(call_data)
    method_signature = call_data_bin[:4]
    for description in contract_abi:
        if description.get('type') != 'function':
            continue
        method_name = normalize_abi_method_name(description['name'])
        arg_types = [item['type'] for item in description['inputs']]
        method_id = get_abi_method_id(method_name, arg_types)
        if zpad(encode_int(method_id), 4) == method_signature:
            args = decode_abi(arg_types, call_data_bin[4:])
            return method_name, args
