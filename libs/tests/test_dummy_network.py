GENERATE_CLIENTS = 5


def test_dummy_network(web3, generate_dummy_network):
    network, clients = generate_dummy_network(GENERATE_CLIENTS)
    assert network is not None
    assert len(clients) == GENERATE_CLIENTS

    c1, c2 = clients[:2]
    c1.open_channel(c2.address)

    c1.transport.send_message(
        c1.get_balance_proof(c2.address, transferred_amount=1),
        c2.address,
    )

    assert len(c2.transport.received_messages) == 1
