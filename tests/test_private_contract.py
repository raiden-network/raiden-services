from raiden_libs.private_contract import PrivateContract


def test_private_contract(
    standard_token_contract,
    generate_raiden_clients,
    wait_for_transaction
):
    client1, client2 = generate_raiden_clients(2)
    private_contract = PrivateContract(standard_token_contract)
    balance = private_contract.functions.balanceOf(client1.address).call()
    tx_hash = private_contract.functions.transfer(client2.address, balance).transact(
        private_key=client1.privkey
    )

    wait_for_transaction(tx_hash)
    balance = private_contract.functions.balanceOf(client1.address).call()
    assert balance == 0
