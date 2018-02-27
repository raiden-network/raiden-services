def test_state_db(state_db, get_random_bp):
    bp = get_random_bp()
    bp = bp.serialize_data()
    state_db.store_balance_proof(bp)
    ret = state_db.balance_proofs
    assert bp['channel_address'] in ret
