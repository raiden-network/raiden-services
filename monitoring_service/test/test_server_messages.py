
def test_bp_dispatch(monitoring_service, get_random_bp):
    """Test if server accepts an incoming balance proof message"""
    monitoring_service.start()
    transport = monitoring_service.transport
    msg = get_random_bp()

    transport.send_message(msg)
    assert msg.channel_address in monitoring_service.balance_proofs


def test_old_bp_dispatch(monitoring_service, get_random_bp):
    """Server should discard messages that are too old"""
    monitoring_service.start()
    transport = monitoring_service.transport
    msg = get_random_bp()
    msg.timestamp = 0

    transport.send_message(msg)
    assert msg.channel_address not in monitoring_service.balance_proofs
