def test_state_db_sqlite(state_db_sqlite, get_random_bp):
    bp = get_random_bp()
    bp = bp.serialize_data()
    state_db_sqlite.store_balance_proof(bp)
    ret = state_db_sqlite.balance_proofs
    fields_to_check = [
        'contract_address',
        'participant1',
        'participant2',
        'nonce',
        'transferred_amount',
        'extra_hash',
        'signature',
        'timestamp',
        'chain_id'
    ]
    for x in fields_to_check:
        assert bp[x] == ret[bp['channel_id']][x]
