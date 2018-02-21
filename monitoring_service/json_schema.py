BALANCE_PROOF_SCHEMA = {
    'type': 'object',
    'required': ['channel_address', 'participant1', 'participant2', 'balance_proof', 'timestamp'],
    'properties': {
        'channel_address': {
            'type': 'string',
        },
        'participant1': {
            'type': 'string'
        },
        'participant2': {
            'type': 'string'
        },
        'balance_proof': {
            'type': 'string',
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
