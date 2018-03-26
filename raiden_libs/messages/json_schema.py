BALANCE_PROOF_SCHEMA = {
    'type': 'object',
    'required': [
        'channel_id', 'contract_address', 'participant1', 'participant2',
        'timestamp', 'extra_hash', 'transferred_amount', 'nonce', 'chain_id'
    ],
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
        'participant1': {
            'type': 'string'
        },
        'participant2': {
            'type': 'string'
        },
        'timestamp': {
            'type': 'number',
        }
    }
}

ENVELOPE_SCHEMA = {
    'type': 'object',
    'required': ['signature', 'data'],
    'properties': {
        'signature': {
            'type': 'string'
        },
        'data': {
            'type': 'string'
        }
    }
}
