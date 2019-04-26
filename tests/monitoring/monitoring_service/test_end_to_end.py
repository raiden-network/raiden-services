import gevent
from eth_utils import encode_hex
from request_collector.server import RequestCollector
from web3 import Web3

from monitoring_service.service import MonitoringService
from monitoring_service.states import HashedBalanceProof
from raiden.utils.typing import BlockNumber, ChainID, Nonce, TokenAmount
from raiden_contracts.constants import CONTRACT_MONITORING_SERVICE, MonitoringServiceEvent
from raiden_contracts.contract_manager import ContractManager
from raiden_contracts.tests.utils.constants import EMPTY_LOCKSROOT
from raiden_libs.blockchain import query_blockchain_events
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
    monitoring_service_contract,
    user_deposit_contract,
    wait_for_blocks,
    service_registry,
    monitoring_service: MonitoringService,
    request_collector: RequestCollector,
    contracts_manager,
    deposit_to_udc,
    create_channel,
    token_network,
    get_accounts,
    get_private_key,
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
    c1, c2 = get_accounts(2)

    # add deposit for c1
    node_deposit = 10
    deposit_to_udc(c1, node_deposit)

    deposit = service_registry.functions.deposits(monitoring_service.address).call()
    assert deposit > 0

    # each client does a transfer
    channel_id = create_channel(c1, c2, settle_timeout=5)[
        0
    ]  # TODO: reduce settle_timeout to speed up test

    shared_bp_args = dict(
        channel_identifier=channel_id,
        token_network_address=token_network.address,
        chain_id=ChainID(1),
        additional_hash="0x%064x" % 0,
        locked_amount=TokenAmount(0),
        locksroot=encode_hex(EMPTY_LOCKSROOT),
    )
    transferred_c1 = 5
    balance_proof_c1 = HashedBalanceProof(
        nonce=Nonce(1),
        transferred_amount=transferred_c1,
        priv_key=get_private_key(c1),
        **shared_bp_args
    )
    transferred_c2 = 6
    balance_proof_c2 = HashedBalanceProof(
        nonce=Nonce(2),
        transferred_amount=transferred_c2,
        priv_key=get_private_key(c2),
        **shared_bp_args
    )

    ms_greenlet = gevent.spawn(monitoring_service.start, gevent.sleep)

    # need to wait here till the MS has some time to react
    gevent.sleep()

    assert monitoring_service.context.ms_state.blockchain_state.token_network_addresses

    # c1 asks MS to monitor the channel
    reward_amount = TokenAmount(1)
    request_monitoring = balance_proof_c2.get_request_monitoring(
        get_private_key(c1), reward_amount
    )
    request_collector.on_monitor_request(request_monitoring)

    # c2 closes the channel
    token_network.functions.closeChannel(
        channel_id,
        c1,
        balance_proof_c1.balance_hash,
        balance_proof_c1.nonce,
        balance_proof_c1.additional_hash,
        balance_proof_c1.signature,
    ).transact({"from": c2})
    # Wait until the MS reacts, which it does after giving the client some time
    # to update the channel itself.
    wait_for_blocks(3)  # 1 block for close + 30% of 5 blocks = 2
    # Now give the monitoring service a chance to submit the missing BP
    gevent.sleep(0.1)

    assert [e.event for e in query()] == [MonitoringServiceEvent.NEW_BALANCE_PROOF_RECEIVED]

    # wait for settle timeout
    wait_for_blocks(2)  # timeout is 5, but we've already waited 3 blocks before

    token_network.functions.settleChannel(
        channel_id,
        c1,  # participant_B
        transferred_c1,  # participant_B_transferred_amount
        0,  # participant_B_locked_amount
        EMPTY_LOCKSROOT,  # participant_B_locksroot
        c2,  # participant_A
        transferred_c2,  # participant_A_transferred_amount
        0,  # participant_A_locked_amount
        EMPTY_LOCKSROOT,  # participant_A_locksroot
    ).transact()

    # Wait until the ChannelSettled is confirmed
    # Let the MS claim its reward
    gevent.sleep(0.1)
    assert [e.event for e in query()] == [
        MonitoringServiceEvent.NEW_BALANCE_PROOF_RECEIVED,
        MonitoringServiceEvent.REWARD_CLAIMED,
    ]

    final_balance = user_deposit_contract.functions.balances(monitoring_service.address).call()
    assert final_balance == (initial_balance + reward_amount)

    ms_greenlet.kill()
