from monitoring_service.tasks import StoreBalanceProof


def test_validate_bp(web3, generate_raiden_client, get_random_address, state_db_sqlite):
    c1, c2 = generate_raiden_client(), generate_raiden_client()
    channel_id = c1.open_channel(c2.address)

    balance_proof = c1.get_balance_proof(c2.address, transferred_amount=1, nonce=1)

    # test happy case: balance proof is valid
    task = StoreBalanceProof(web3, state_db_sqlite, balance_proof)
    assert task._run() is True

    # balance proof with an invalid contract address
    balance_proof.contract_address = get_random_address()
    task = StoreBalanceProof(web3, state_db_sqlite, balance_proof)
    task._run()
    assert task._run() is False

    # balance proof with an invalid timestamp
    balance_proof.timestamp = -1
    balance_proof.channel_id = channel_id
    task = StoreBalanceProof(web3, state_db_sqlite, balance_proof)
    task._run()
    assert task._run() is False
