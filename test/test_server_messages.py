from monitoring_service.messages import BalanceProof


def test_message_dispatch(monitoring_service, get_random_address):
    monitoring_service.start()
    transport = monitoring_service.transport
    p1, p2 = get_random_address(), get_random_address()
    channel_address = get_random_address()
    msg = BalanceProof(channel_address, p1, p2)

    transport.send_message(msg)
