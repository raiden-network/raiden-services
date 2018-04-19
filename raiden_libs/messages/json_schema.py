def make_properties_required(schema):
    schema['required'] = list(schema['properties'].keys())


BALANCE_PROOF_SCHEMA = {
    'type': 'object',
    'required': [],
    'properties': {
        'channel_id': {
            'type': 'integer',
        },
        'nonce': {
            'type': 'integer',
        },
        'chain_id': {
            'type': 'integer',
        },
        'contract_address': {
            'type': 'string'
        },
        'extra_hash': {
            'type': 'string'
        },
        'transferred_amount': {
            'type': 'integer'
        },
        'timestamp': {
            'type': 'number',
        }
    }
}
make_properties_required(BALANCE_PROOF_SCHEMA)

MONITOR_REQUEST_SCHEMA = {
    'type': 'object',
    'required': [],
    'properties': {
        'channel_identifier': {
            'type': 'integer',
            'minimum': 1
        },
        'nonce': {
            'type': 'integer',
            'minimum': 0
        },
        'transferred_amount': {
            'type': 'integer'
        },
        'locksroot': {
            'type': 'string'
        },
        'extra_hash': {
            'type': 'string'
        },
        'balance_proof_signature': {
            'type': 'string'
        },
        'reward_sender_address': {
            'type': 'string'
        },
        'reward_proof_signature': {
            'type': 'string',
        },
        'reward_amount': {
            'type': 'integer',
        },
        'token_network_address': {
            'type': 'string',
        },
        'monitor_address': {
            'type': 'string',
        },
        'chain_id': {
            'type': 'integer',
        }
    }
}
make_properties_required(MONITOR_REQUEST_SCHEMA)

FEE_INFO_SCHEMA = {
    'type': 'object',
    'required': [
        'token_network_address',
        'chain_id',
        'channel_identifier',
        'nonce',
        'percentage_fee',
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
            'type': 'integer',
            'minimum': 1
        },
        'nonce': {
            'type': 'integer',
            'minimum': 0
        },
        'percentage_fee': {
            'type': 'string',
        },
        'signature': {
            'type': 'string'
        },
    }
}

ENVELOPE_SCHEMA = {
    'type': 'object',
    'required': ['message_type'],
    'properties': {
        'message_type': {
            'type': 'string'
        }
    }
}
