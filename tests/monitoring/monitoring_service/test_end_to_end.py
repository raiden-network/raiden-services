from typing import Callable

import gevent
from eth_utils import decode_hex, encode_hex, to_canonical_address
from request_collector.server import RequestCollector
from web3 import Web3

from monitoring_service.service import MonitoringService, handle_event
from monitoring_service.states import HashedBalanceProof
from raiden.utils.typing import (
    Address,
    BlockNumber,
    MonitoringServiceAddress,
    Nonce,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    LOCKSROOT_OF_NO_LOCKS,
    MonitoringServiceEvent,
)
from raiden_contracts.contract_manager import ContractManager
from raiden_libs.blockchain import query_blockchain_events


def create_ms_contract_events_query(
    web3: Web3, contract_manager: ContractManager, contract_address: Address
) -> Callable:
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


def test_first_allowed_monitoring(
    web3: Web3,
    monitoring_service_contract,
    wait_for_blocks,
    service_registry,
    monitoring_service: MonitoringService,
    request_collector: RequestCollector,
    contracts_manager: ContractManager,
    deposit_to_udc,
    create_channel,
    token_network,
    get_accounts,
    get_private_key,
):
    # pylint: disable=too-many-arguments,too-many-locals,protected-access
    query = create_ms_contract_events_query(
        web3, contracts_manager, monitoring_service_contract.address
    )
    c1, c2 = get_accounts(2)

    # add deposit for c1
    node_deposit = 10
    deposit_to_udc(c1, node_deposit)

    assert service_registry.functions.hasValidRegistration(monitoring_service.address).call()

    # each client does a transfer
    channel_id = create_channel(c1, c2, settle_timeout=10)[0]

    shared_bp_args = dict(
        channel_identifier=channel_id,
        token_network_address=decode_hex(token_network.address),
        chain_id=monitoring_service.chain_id,
        additional_hash="0x%064x" % 0,
        locked_amount=TokenAmount(0),
        locksroot=encode_hex(LOCKSROOT_OF_NO_LOCKS),
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
    monitoring_service._process_new_blocks(web3.eth.blockNumber)
    assert len(monitoring_service.context.database.get_token_network_addresses()) > 0

    # c1 asks MS to monitor the channel
    reward_amount = TokenAmount(1)
    request_monitoring = balance_proof_c2.get_request_monitoring(
        privkey=get_private_key(c1),
        reward_amount=reward_amount,
        monitoring_service_contract_address=MonitoringServiceAddress(
            to_canonical_address(monitoring_service_contract.address)
        ),
    )
    request_collector.on_monitor_request(request_monitoring)

    # c2 closes the channel
    token_network.functions.closeChannel(
        channel_id,
        c1,
        c2,
        balance_proof_c1.balance_hash,
        balance_proof_c1.nonce,
        balance_proof_c1.additional_hash,
        balance_proof_c1.signature,
        balance_proof_c1.get_counter_signature(get_private_key(c2)),
    ).transact({"from": c2})

    monitoring_service._process_new_blocks(web3.eth.blockNumber)
    triggered_events = monitoring_service.database.get_scheduled_events(
        max_trigger_block=BlockNumber(web3.eth.blockNumber + 10)
    )
    assert len(triggered_events) == 1

    monitor_trigger = triggered_events[0]
    channel = monitoring_service.database.get_channel(
        token_network_address=TokenNetworkAddress(to_canonical_address(token_network.address)),
        channel_id=channel_id,
    )
    assert channel

    # Calling monitor too early must fail. To test this, we call it two block
    # before the trigger block.
    # This should be only one block before, but we trigger one block too late
    # to work around parity's gas estimation. See
    # https://github.com/raiden-network/raiden-services/pull/728
    wait_for_blocks(monitor_trigger.trigger_block_number - web3.eth.blockNumber - 2)
    handle_event(monitor_trigger.event, monitoring_service.context)
    assert [e.event for e in query()] == []

    # If our `monitor` call fails, we won't try again. Force a retry in this
    # test by clearing monitor_tx_hash.
    channel.monitor_tx_hash = None
    monitoring_service.database.upsert_channel(channel)

    # Now we can try again. The first try mined a new block, so now we're one
    # block further and `monitor` should succeed.
    handle_event(monitor_trigger.event, monitoring_service.context)
    assert [e.event for e in query()] == [MonitoringServiceEvent.NEW_BALANCE_PROOF_RECEIVED]


def test_e2e(  # pylint: disable=too-many-arguments,too-many-locals
    web3,
    monitoring_service_contract,
    user_deposit_contract,
    wait_for_blocks,
    service_registry,
    monitoring_service: MonitoringService,
    request_collector: RequestCollector,
    contracts_manager: ContractManager,
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

    assert service_registry.functions.hasValidRegistration(monitoring_service.address).call()

    # each client does a transfer
    channel_id = create_channel(c1, c2, settle_timeout=5)[0]

    shared_bp_args = dict(
        channel_identifier=channel_id,
        token_network_address=decode_hex(token_network.address),
        chain_id=monitoring_service.chain_id,
        additional_hash="0x%064x" % 0,
        locked_amount=TokenAmount(0),
        locksroot=encode_hex(LOCKSROOT_OF_NO_LOCKS),
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
    gevent.sleep(0.01)
    assert len(monitoring_service.context.database.get_token_network_addresses()) > 0

    # c1 asks MS to monitor the channel
    reward_amount = TokenAmount(1)
    request_monitoring = balance_proof_c2.get_request_monitoring(
        privkey=get_private_key(c1),
        reward_amount=reward_amount,
        monitoring_service_contract_address=MonitoringServiceAddress(
            to_canonical_address(monitoring_service_contract.address)
        ),
    )
    request_collector.on_monitor_request(request_monitoring)

    # c2 closes the channel
    token_network.functions.closeChannel(
        channel_id,
        c1,
        c2,
        balance_proof_c1.balance_hash,
        balance_proof_c1.nonce,
        balance_proof_c1.additional_hash,
        balance_proof_c1.signature,
        balance_proof_c1.get_counter_signature(get_private_key(c2)),
    ).transact({"from": c2})
    # Wait until the MS reacts, which it does after giving the client some time
    # to update the channel itself.

    wait_for_blocks(2)  # 1 block for close + 1 block for triggering the event
    # Now give the monitoring service a chance to submit the missing BP
    gevent.sleep(0.01)
    assert [e.event for e in query()] == [MonitoringServiceEvent.NEW_BALANCE_PROOF_RECEIVED]

    # wait for settle timeout
    # timeout is 5, but we've already waited 3 blocks before. Additionally one block is
    # added to handle parity running gas estimation on current instead of next.
    wait_for_blocks(3)

    # Let the MS claim its reward
    gevent.sleep(0.01)
    assert [e.event for e in query()] == [
        MonitoringServiceEvent.NEW_BALANCE_PROOF_RECEIVED,
        MonitoringServiceEvent.REWARD_CLAIMED,
    ]

    final_balance = user_deposit_contract.functions.balances(monitoring_service.address).call()
    assert final_balance == (initial_balance + reward_amount)

    ms_greenlet.kill()
