from monitoring_service.tasks import OnChannelSettle
from raiden_libs.utils import private_key_to_address
from raiden_libs.private_contract import PrivateContract


def test_on_channel_settle(
    web3,
    generate_raiden_clients,
    get_random_privkey,
    monitoring_service_contract,
    send_funds
):
    c1, c2 = generate_raiden_clients(2)
    ms_privkey = get_random_privkey()
    ms_address = private_key_to_address(ms_privkey)
    send_funds(ms_address)
    c1.open_channel(c2.address)
    balance_proof = c1.get_balance_proof(c2.address, transferred_amount=1)
    monitor_request = c2.get_monitor_request(
        c1.address,
        balance_proof,
        1,
        ms_address
    )

    task = OnChannelSettle(
        monitor_request,
        PrivateContract(monitoring_service_contract),
        ms_privkey
    )

    assert task._run() is True
