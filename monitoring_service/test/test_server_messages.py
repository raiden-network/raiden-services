
def test_bp_dispatch(monitoring_service, generate_raiden_client):
    """Test if server accepts an incoming balance proof message"""
    c1, c2 = generate_raiden_client(), generate_raiden_client()
    channel_id = c1.open_channel(c2.address)
    msg = c1.get_balance_proof(c2.address, transferred_amount=1)
    monitoring_service.start()
    transport = monitoring_service.transport

    transport.send_message(msg)
    monitoring_service.wait_tasks()
    assert channel_id in monitoring_service.balance_proofs


def test_old_bp_dispatch(monitoring_service, generate_raiden_client):
    """Server should discard messages that are too old"""
    c1, c2 = generate_raiden_client(), generate_raiden_client()
    channel_id = c1.open_channel(c2.address)
    msg = c1.get_balance_proof(c2.address, transferred_amount=1)

    monitoring_service.start()
    transport = monitoring_service.transport
    msg.timestamp = 0

    transport.send_message(msg)
    assert channel_id not in monitoring_service.balance_proofs
