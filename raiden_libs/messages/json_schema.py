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

MONITOR_REQUEST_SCHEMA = {
    'type': 'object',
    'required': [
        'channel_identifier', 'nonce', 'transferred_amount', 'locksroot',
        'extra_hash', 'signature',
        'reward_sender_address', 'reward_proof_signature', 'reward_amount',
        'token_network_address', 'chain_id', 'monitor_address'
    ],
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
        'signature': {
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

ENVELOPE_SCHEMA = {
    'type': 'object',
    'required': ['message_type'],
    'properties': {
        'message_type': {
            'type': 'string'
        }
    }
}
