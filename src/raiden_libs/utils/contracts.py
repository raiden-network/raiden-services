from typing import Dict, Optional, Tuple

from eth_abi import decode_abi
from eth_utils import decode_hex, function_abi_to_4byte_selector


def normalize_name(name: str) -> str:
    """ Return normalized event/function name. """
    if '(' in name:
        return name[:name.find('(')]

    return name


def decode_contract_call(contract_abi: list, call_data: str) -> Optional[Tuple[str, Dict]]:
    call_data_bin = decode_hex(call_data)
    method_signature = call_data_bin[:4]
    for description in contract_abi:
        if description.get('type') != 'function':
            continue
        method_id = function_abi_to_4byte_selector(description)
        method_name = normalize_name(description['name'])
        arg_types = [item['type'] for item in description['inputs']]
        if method_id == method_signature:
            args = decode_abi(arg_types, call_data_bin[4:])
            return method_name, args

    return None
