from monitoring_service.tasks import StoreBalanceProof


def test_validate_bp(web3, generate_raiden_client, get_random_address, state_db):
    c1, c2 = generate_raiden_client(), generate_raiden_client()
    channel_address = c1.open_channel(c2.address)

    balance_proof = c1.get_balance_proof(c2.address, 1)

    # test happy case: balance proof is valid
    task = StoreBalanceProof(web3, state_db, balance_proof)
    assert task._run() is True

    # balance proof with an invalid channel address
    balance_proof.channel_address = get_random_address()
    task = StoreBalanceProof(web3, state_db, balance_proof)
    task._run()
    assert task._run() is False

    # balance proof with an invalid timestamp
    balance_proof.timestamp = -1
    balance_proof.channel_address = channel_address
    task = StoreBalanceProof(web3, state_db, balance_proof)
    task._run()
    assert task._run() is False
