import gevent
from request_collector.server import RequestCollector
from web3 import Web3

from monitoring_service.blockchain import query_blockchain_events
from monitoring_service.service import MonitoringService
from raiden.utils.typing import BlockNumber
from raiden_contracts.constants import CONTRACT_MONITORING_SERVICE, MonitoringServiceEvent
from raiden_contracts.contract_manager import ContractManager
from raiden_libs.types import Address


def create_ms_contract_events_query(
    web3: Web3, contract_manager: ContractManager, contract_address: Address
):
    def f():
        return query_blockchain_events(
            web3=web3,
            contract_manager=contract_manager,
            contract_address=contract_address,
            contract_name=CONTRACT_MONITORING_SERVICE,
            topics=[],
            from_block=BlockNumber(0),
            to_block=web3.eth.blockNumber,
        )

    return f


def test_e2e(
    web3,
    generate_raiden_clients,
    monitoring_service_contract,
    user_deposit_contract,
    wait_for_blocks,
    custom_token,
    service_registry,
    monitoring_service: MonitoringService,
    request_collector: RequestCollector,
    contracts_manager,
):
    """Test complete message lifecycle
        1) client opens channel & submits monitoring request
        2) other client closes channel
        3) MS registers channelClose event
        4) MS calls monitoring contract update
        5) wait for channel settle
        6) MS claims the reward
    """
    query = create_ms_contract_events_query(
        web3, contracts_manager, monitoring_service_contract.address
    )
    initial_balance = user_deposit_contract.functions.balances(monitoring_service.address).call()
    c1, c2 = generate_raiden_clients(2)

    # add deposit for c1
    node_deposit = 10
    custom_token.functions.approve(user_deposit_contract.address, node_deposit).transact(
        {'from': c1.address}
    )
    user_deposit_contract.functions.deposit(c1.address, node_deposit).transact(
        {'from': c1.address}
    )

    deposit = service_registry.functions.deposits(monitoring_service.address).call()
    assert deposit > 0

    # each client does a transfer
    c1.open_channel(c2.address)
    transferred_c1 = 5
    balance_proof_c1 = c1.get_balance_proof(
        c2.address,
        nonce=1,
        transferred_amount=transferred_c1,
        locked_amount=0,
        locksroot='0x%064x' % 0,
        additional_hash='0x%064x' % 0,
    )
    transferred_c2 = 6
    balance_proof_c2 = c2.get_balance_proof(
        c1.address,
        nonce=2,
        transferred_amount=transferred_c2,
        locked_amount=0,
        locksroot='0x%064x' % 0,
        additional_hash='0x%064x' % 0,
    )
    ms_greenlet = gevent.spawn(monitoring_service.start, gevent.sleep)

    # need to wait here till the MS has some time to react
    gevent.sleep()

    assert monitoring_service.context.ms_state.blockchain_state.token_network_addresses

    # c1 asks MS to monitor the channel
    reward_amount = 1
    request_monitoring = c1.get_request_monitoring(balance_proof_c2, reward_amount)
    request_collector.on_monitor_request(request_monitoring)

    # c2 closes the channel
    c2.close_channel(c1.address, balance_proof_c1)
    # Wait until the MS reacts, which it does after giving the client some time
    # to update the channel itself.
    wait_for_blocks(5)  # 30% of 15 blocks
    # Now give the monitoring service a chance to submit the missing BP
    gevent.sleep(0.1)

    assert [e.event for e in query()] == [MonitoringServiceEvent.NEW_BALANCE_PROOF_RECEIVED.value]

    # wait for settle timeout
    wait_for_blocks(15)
    c2.settle_channel(
        c1.address,
        (transferred_c2, transferred_c1),
        (0, 0),  # locked_amount
        ('0x%064x' % 0, '0x%064x' % 0),  # locksroot
    )
    # Wait until the ChannelSettled is confirmed
    # Let the MS claim its reward
    gevent.sleep(0.1)
    assert [e.event for e in query()] == [
        MonitoringServiceEvent.NEW_BALANCE_PROOF_RECEIVED.value,
        MonitoringServiceEvent.REWARD_CLAIMED.value,
    ]

    final_balance = user_deposit_contract.functions.balances(monitoring_service.address).call()
    assert final_balance == (initial_balance + reward_amount)

    ms_greenlet.kill()
