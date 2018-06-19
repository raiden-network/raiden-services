import functools

from web3.utils.events import get_event_data
from web3.utils.filters import construct_event_filter_params
from eth_utils import (
    decode_hex,
    function_abi_to_4byte_selector,
)
from eth_abi import decode_abi


def normalize_name(name):
    """ Return normalized event/function name. """
    if '(' in name:
        return name[:name.find('(')]

    return name


def make_filter(web3, event_abi, filters=None, **filter_kwargs):
    assert event_abi != []
    log_data_extract_fn = functools.partial(get_event_data, event_abi)
    data_filter_set, filter_params = construct_event_filter_params(
        event_abi,
        argument_filters=filters,
        **filter_kwargs,
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
        method_id = function_abi_to_4byte_selector(description)
        method_name = normalize_name(description['name'])
        arg_types = [item['type'] for item in description['inputs']]
        if method_id == method_signature:
            args = decode_abi(arg_types, call_data_bin[4:])
            return method_name, args
