from datetime import datetime
from typing import Callable

import gevent
from eth_utils import decode_hex, encode_hex, to_canonical_address
from web3 import Web3

from monitoring_service.handlers import _first_allowed_timestamp_to_monitor
from monitoring_service.service import MonitoringService, handle_event
from monitoring_service.states import HashedBalanceProof
from raiden.utils.typing import (
    Address,
    BlockNumber,
    MonitoringServiceAddress,
    Nonce,
    Timestamp,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_contracts.constants import LOCKSROOT_OF_NO_LOCKS, MonitoringServiceEvent
from raiden_libs.blockchain import query_blockchain_events
from request_collector.server import RequestCollector


def create_ms_contract_events_query(web3: Web3, contract_address: Address) -> Callable:
    def f():
        return query_blockchain_events(
            web3=web3,
            contract_addresses=[contract_address],
            from_block=BlockNumber(0),
            to_block=web3.eth.block_number,
        )

    return f


def test_first_allowed_monitoring(
    web3: Web3,
    monitoring_service_contract,
    service_registry,
    monitoring_service: MonitoringService,
    request_collector: RequestCollector,
    deposit_to_udc,
    create_channel,
    token_network,
    get_accounts,
    get_private_key,
):
    # pylint: disable=too-many-arguments,too-many-locals,protected-access
    query = create_ms_contract_events_query(web3, monitoring_service_contract.address)
    c1, c2 = get_accounts(2)

    # add deposit for c1
    node_deposit = 10
    deposit_to_udc(c1, node_deposit)

    assert service_registry.functions.hasValidRegistration(monitoring_service.address).call()

    # each client does a transfer
    channel_id = create_channel(c1, c2)[0]

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
        **shared_bp_args,
    )
    transferred_c2 = 6
    balance_proof_c2 = HashedBalanceProof(
        nonce=Nonce(2),
        transferred_amount=transferred_c2,
        priv_key=get_private_key(c2),
        **shared_bp_args,
    )
    monitoring_service._process_new_blocks(web3.eth.block_number)
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

    monitoring_service._process_new_blocks(web3.eth.block_number)

    timestamp_of_closing_block = Timestamp(web3.eth.get_block("latest").timestamp)  # type: ignore
    settle_timeout = int(token_network.functions.settle_timeout().call())
    settleable_after = Timestamp(timestamp_of_closing_block + settle_timeout)

    triggered_events = monitoring_service.database.get_scheduled_events(
        max_trigger_timestamp=settleable_after
    )

    assert len(triggered_events) == 1

    monitor_trigger = triggered_events[0]
    channel = monitoring_service.database.get_channel(
        token_network_address=TokenNetworkAddress(to_canonical_address(token_network.address)),
        channel_id=channel_id,
    )
    assert channel

    # Calling monitor too early must fail. To test this, we call a few seconds
    # before the trigger timestamp.
    web3.testing.timeTravel(monitor_trigger.trigger_timestamp - 5)  # type: ignore

    handle_event(monitor_trigger.event, monitoring_service.context)
    assert [e.event for e in query()] == []

    # If our `monitor` call fails, we won't try again. Force a retry in this
    # test by clearing monitor_tx_hash.
    channel.monitor_tx_hash = None
    monitoring_service.database.upsert_channel(channel)

    # Now we can try again. The first try mined a new block, so now we're one
    # block further and `monitor` should succeed.
    web3.testing.timeTravel(monitor_trigger.trigger_timestamp)  # type: ignore
    handle_event(monitor_trigger.event, monitoring_service.context)
    assert [e.event for e in query()] == [MonitoringServiceEvent.NEW_BALANCE_PROOF_RECEIVED]


def test_reschedule_too_early_events(
    web3: Web3,
    monitoring_service_contract,
    monitoring_service: MonitoringService,
    request_collector: RequestCollector,
    deposit_to_udc,
    create_channel,
    token_network,
    get_accounts,
    get_private_key,
):
    # pylint: disable=too-many-arguments,too-many-locals,protected-access
    c1, c2 = get_accounts(2)

    # add deposit for c1
    node_deposit = 10
    deposit_to_udc(c1, node_deposit)

    # each client does a transfer
    channel_id = create_channel(c1, c2)[0]

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
        **shared_bp_args,
    )
    transferred_c2 = 6
    balance_proof_c2 = HashedBalanceProof(
        nonce=Nonce(2),
        transferred_amount=transferred_c2,
        priv_key=get_private_key(c2),
        **shared_bp_args,
    )
    monitoring_service._process_new_blocks(web3.eth.block_number)
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

    monitoring_service._process_new_blocks(web3.eth.block_number)

    timestamp_of_closing_block = Timestamp(web3.eth.get_block("latest").timestamp)  # type: ignore
    settle_timeout = int(token_network.functions.settle_timeout().call())
    settleable_after = Timestamp(timestamp_of_closing_block + settle_timeout)

    scheduled_events = monitoring_service.database.get_scheduled_events(
        max_trigger_timestamp=settleable_after
    )

    channel = monitoring_service.database.get_channel(
        token_network_address=TokenNetworkAddress(to_canonical_address(token_network.address)),
        channel_id=channel_id,
    )

    monitor_trigger = _first_allowed_timestamp_to_monitor(
        scheduled_events[0].event.token_network_address, channel, monitoring_service.context
    )

    assert len(scheduled_events) == 1
    first_trigger_timestamp = scheduled_events[0].trigger_timestamp
    assert first_trigger_timestamp == monitor_trigger

    # Calling monitor too early must fail
    now = int(datetime.utcnow().timestamp())
    monitoring_service.get_timestamp_now = lambda: settleable_after
    monitoring_service._trigger_scheduled_events()  # pylint: disable=protected-access

    # Failed event is rescheduled to run on the next iteration
    scheduled_events = monitoring_service.database.get_scheduled_events(settleable_after + 10)
    assert len(scheduled_events) == 1
    assert scheduled_events[0].trigger_timestamp > now


def test_e2e(  # pylint: disable=too-many-arguments,too-many-locals
    web3,
    monitoring_service_contract,
    user_deposit_contract,
    service_registry,
    monitoring_service: MonitoringService,
    request_collector: RequestCollector,
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
    query = create_ms_contract_events_query(web3, monitoring_service_contract.address)
    initial_balance = user_deposit_contract.functions.balances(monitoring_service.address).call()
    c1, c2 = get_accounts(2)

    # add deposit for c1
    node_deposit = 10
    deposit_to_udc(c1, node_deposit)

    assert service_registry.functions.hasValidRegistration(monitoring_service.address).call()

    # each client does a transfer
    channel_id = create_channel(c1, c2)[0]

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
        **shared_bp_args,
    )
    transferred_c2 = 6
    balance_proof_c2 = HashedBalanceProof(
        nonce=Nonce(2),
        transferred_amount=transferred_c2,
        priv_key=get_private_key(c2),
        **shared_bp_args,
    )

    ms_greenlet = gevent.spawn(monitoring_service.start)

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

    timestamp_of_closing_block = Timestamp(web3.eth.get_block("latest").timestamp)
    settle_timeout = int(token_network.functions.settle_timeout().call())
    settleable_after = Timestamp(timestamp_of_closing_block + settle_timeout)

    web3.testing.timeTravel(settleable_after - 1)
    monitoring_service.get_timestamp_now = lambda: settleable_after - 1

    # Now give the monitoring service a chance to submit the missing BP
    gevent.sleep(0.01)
    assert [e.event for e in query()] == [MonitoringServiceEvent.NEW_BALANCE_PROOF_RECEIVED]

    # wait for settle timeout
    web3.testing.timeTravel(settleable_after + 1)
    monitoring_service.get_timestamp_now = lambda: settleable_after + 1

    # Let the MS claim its reward
    gevent.sleep(0.01)
    assert [e.event for e in query()] == [
        MonitoringServiceEvent.NEW_BALANCE_PROOF_RECEIVED,
        MonitoringServiceEvent.REWARD_CLAIMED,
    ]

    final_balance = user_deposit_contract.functions.balances(monitoring_service.address).call()
    assert final_balance == (initial_balance + reward_amount)

    ms_greenlet.kill()
