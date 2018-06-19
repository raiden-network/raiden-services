def make_properties_required(schema):
    schema['required'] = list(schema['properties'].keys())


BALANCE_PROOF_SCHEMA = {
    'type': 'object',
    'required': [
        'channel_identifier',
        'nonce',
        'chain_id',
        'token_network_address',
        'balance_hash',
        'additional_hash',
        'signature',
    ],
    'properties': {
        'channel_identifier': {
            'type': 'string',
        },
        'nonce': {
            'type': 'integer',
        },
        'chain_id': {
            'type': 'integer',
        },
        'token_network_address': {
            'type': 'string',
        },
        'balance_hash': {
            'type': 'string',
        },
        'additional_hash': {
            'type': 'string',
        },
        'signature': {
            'type': 'string',
        },
        'transferred_amount': {
            'type': 'integer',
        },
        'locked_amount': {
            'type': 'integer',
        },
        'locksroot': {
            'type': 'string',
        },
    },
}

MONITOR_REQUEST_SCHEMA = {
    'type': 'object',
    'required': [],
    'properties': {
        'reward_proof_signature': {
            'type': 'string',
        },
        'reward_amount': {
            'type': 'integer',
        },
        'monitor_address': {
            'type': 'string',
        },
        'balance_proof': {
            'type': 'object',
        },
    },
}
make_properties_required(MONITOR_REQUEST_SCHEMA)

FEE_INFO_SCHEMA = {
    'type': 'object',
    'required': [
        'token_network_address',
        'chain_id',
        'channel_identifier',
        'nonce',
        'relative_fee',
        'signature',
    ],
    'properties': {
        'token_network_address': {
            'type': 'string',
        },
        'chain_id': {
            'type': 'integer',
        },
        'channel_identifier': {
            'type': 'string',
        },
        'nonce': {
            'type': 'integer',
            'minimum': 0,
        },
        'relative_fee': {
            'type': 'integer',
            'minimum': 0,
        },
        'signature': {
            'type': 'string',
        },
    },
}

PATHS_REQUEST_SCHEMA = {
    'type': 'object',
    'required': [
        'token_network_address',
        'source_address',
        'target_address',
        'value',
        'num_paths',
        'chain_id',
        'nonce',
        'signature',
    ],
    'properties': {
        'token_network_address': {
            'type': 'string',
        },
        'source_address': {
            'type': 'string',
        },
        'target_address': {
            'type': 'string',
        },
        'value': {
            'type': 'integer',
            'minimum': 1,
        },
        'num_paths': {
            'type': 'integer',
            'minimum': 1,
        },
        'chain_id': {
            'type': 'integer',
            'minimum': 1,
        },
        'nonce': {
            'type': 'integer',
            'minimum': 0,
        },
        'signature': {
            'type': 'string',
        },
    },
}

PATHS_REPLY_SCHEMA = {
    'type': 'object',
    'required': [
        'token_network_address',
        'target_address',
        'value',
        'chain_id',
        'nonce',
        'paths_and_fees',
        'signature',
    ],
    'properties': {
        'token_network_address': {
            'type': 'string',
        },
        'target_address': {
            'type': 'string',
        },
        'value': {
            'type': 'integer',
            'minimum': 1,
        },
        'chain_id': {
            'type': 'integer',
            'minimum': 1,
        },
        'nonce': {
            'type': 'integer',
            'minimum': 0,
        },
        'paths_and_fees': {
            'type': 'array',
        },
        'signature': {
            'type': 'string',
        },
    },
}

ENVELOPE_SCHEMA = {
    'type': 'object',
    'required': ['message_type'],
    'properties': {
        'message_type': {
            'type': 'string',
        },
    },
}
