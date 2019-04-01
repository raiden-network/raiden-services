def make_properties_required(schema: dict) -> None:
    schema['required'] = list(schema['properties'].keys())


MONITOR_REQUEST_SCHEMA = {
    'type': 'object',
    'required': [],
    'properties': {
        'reward_proof_signature': {'type': 'string'},
        'reward_amount': {'type': 'integer'},
        'balance_proof': {'type': 'object'},
    },
}
make_properties_required(MONITOR_REQUEST_SCHEMA)
