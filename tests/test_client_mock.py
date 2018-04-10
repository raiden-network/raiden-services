

def test_client_multiple_topups(generate_raiden_clients):
    deposits = [1, 1, 2, 3, 5, 8, 13]
    c1, c2 = generate_raiden_clients(2)
    channel_id = c1.open_channel(c2.address)
    assert channel_id > 0
    [c1.deposit_to_channel(c2.address, x) for x in deposits]
    channel_info = c1.get_channel_participant_info(c2.address)
    assert sum(deposits) == channel_info['deposit']
