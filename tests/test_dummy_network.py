GENERATE_CLIENTS = 5


def test_dummy_network(web3, generate_dummy_network):
    network, clients = generate_dummy_network(GENERATE_CLIENTS)
    assert network is not None
    assert len(clients) == GENERATE_CLIENTS

    messages_received = []

    c1, c2 = clients[:2]
    c1.open_channel(c2.address)

    c2.transport.add_message_callback(lambda x: messages_received.append(x))

    c1.transport.send_message(
        c1.get_balance_proof(c2.address, transferred_amount=1),
        c2.address,
    )

    assert len(messages_received) == 1
