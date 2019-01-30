from typing import Dict, List

import gevent
import pytest
import structlog
from eth_utils import encode_hex

import raiden_libs.messages
from monitoring_service.service import MonitoringService
from monitoring_service.states import MonitorRequest
from raiden_contracts.constants import CONTRACT_MONITORING_SERVICE, MonitoringServiceEvent, CONTRACT_TOKEN_NETWORK
from raiden_contracts.contract_manager import ContractManager
from raiden_libs.blockchain import BlockchainListener

TEST_POLL_INTERVAL = 0.1
log = structlog.get_logger(__name__)


class Validator(BlockchainListener):
    def __init__(
        self,
        web3,
        contracts_manager: ContractManager,
    ):
        super().__init__(
            web3,
            contracts_manager,
            CONTRACT_MONITORING_SERVICE,
            poll_interval=0.001,
        )
        self.events: List[Dict] = list()
        self.add_unconfirmed_listener(
            MonitoringServiceEvent.NEW_BALANCE_PROOF_RECEIVED, self.events.append,
        )
        self.add_unconfirmed_listener(
            MonitoringServiceEvent.REWARD_CLAIMED, self.events.append,
        )


@pytest.fixture
def blockchain_validator(
        web3,
        contracts_manager,
):
    validator = Validator(web3, contracts_manager)
    validator.start()
    yield validator
    validator.stop()


def test_e2e(
    web3,
    generate_raiden_clients,
    monitoring_service_contract,
    user_deposit_contract,
    wait_for_blocks,
    custom_token,
    raiden_service_bundle,
    monitoring_service: MonitoringService,
    blockchain_validator,
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
    user_deposit_contract.functions.init(monitoring_service_contract.address).transact()
    user_deposit_contract.functions.balances(
        monitoring_service.address,
    ).call()
    c1, c2 = generate_raiden_clients(2)

    # add deposit for c1
    # TODO: this should be done via RSB at some point
    node_deposit = 10
    custom_token.functions.approve(
        user_deposit_contract.address,
        node_deposit,
    ).transact({'from': c1.address})
    user_deposit_contract.functions.deposit(
        c1.address, node_deposit,
    ).transact({'from': c1.address})

    # each client does a transfer
    c1.open_channel(c2.address)
    balance_proof_c1 = c1.get_balance_proof(
        c2.address,
        nonce=1,
        transferred_amount=5,
        locked_amount=0,
        locksroot='0x%064x' % 0,
        additional_hash='0x%064x' % 0,
    )
    balance_proof_c2 = c2.get_balance_proof(
        c1.address,
        nonce=2,
        transferred_amount=6,
        locked_amount=0,
        locksroot='0x%064x' % 0,
        additional_hash='0x%064x' % 0,
    )

    ms_greenlet = gevent.spawn(monitoring_service.start, gevent.sleep)

    # need to wait here till the MS has some time to react
    gevent.sleep()

    assert monitoring_service.ms_state.blockchain_state.token_network_addresses

    ms_greenlet.kill()
    # c1 asks MS to monitor the channel
    reward_amount = 1
    monitor_request: raiden_libs.messages.MonitorRequest = c1.get_monitor_request(
        c2.address,
        balance_proof_c2,
        reward_amount,
        monitoring_service.address,
    )
    # wait for channel open event to be processed by the MS
    wait_for_blocks(1)
    gevent.sleep(0)

    mr = MonitorRequest(
        channel_identifier=monitor_request.balance_proof.channel_identifier,
        token_network_address=monitor_request.balance_proof.token_network_address,
        chain_id=monitor_request.balance_proof.chain_id,
        balance_hash=monitor_request.balance_proof.balance_hash,
        nonce=monitor_request.balance_proof.nonce,
        additional_hash=monitor_request.balance_proof.additional_hash,
        closing_signature=monitor_request.balance_proof.signature,
        non_closing_signature=monitor_request.non_closing_signature,
        reward_amount=monitor_request.reward_amount,
        reward_proof_signature=monitor_request.reward_proof_signature,
    )

    assert mr.channel_identifier == monitor_request.balance_proof.channel_identifier
    assert mr.token_network_address == monitor_request.balance_proof.token_network_address
    assert mr.chain_id == monitor_request.balance_proof.chain_id
    assert mr.balance_hash == monitor_request.balance_proof.balance_hash
    assert mr.nonce == monitor_request.balance_proof.nonce
    assert mr.additional_hash == monitor_request.balance_proof.additional_hash
    assert mr.closing_signature == monitor_request.balance_proof.signature
    assert mr.non_closing_signature == monitor_request.non_closing_signature
    assert mr.reward_amount == monitor_request.reward_amount
    assert mr.reward_proof_signature == monitor_request.reward_proof_signature
    assert mr.reward_proof_signer == monitor_request.reward_proof_signer
    assert mr.signer == monitor_request.balance_proof.signer
    assert mr.non_closing_signer == monitor_request.non_closing_signer

    monitoring_service.database.upsert_monitor_request(mr)

    # request_collector.transport.receive_fake_data(monitor_request.serialize_full())
    # gevent.sleep(1)
    # assert (channel_id, c1.address) in monitoring_service.monitor_requests

    # c2 closes the channel
    c2.close_channel(c1.address, balance_proof_c1)
    # Wait one block until the ChannelClosed event is confirmed and handled
    # by the MS
    wait_for_blocks(1)
    # Now give the monitoring service a chance to submit the missing BP
    gevent.sleep(1)

    network_contract = web3.eth.contract(
        abi=contracts_manager.get_contract_abi(
            CONTRACT_TOKEN_NETWORK,
        ),
        address=mr.token_network_address
    )
    channel_data = network_contract.functions.getChannelParticipantInfo(
        mr.channel_identifier,
        c1.address,
        c2.address,
    ).call()

    log.info('channel data non-closer:', data=channel_data)
    channel_data2 = network_contract.functions.getChannelParticipantInfo(
        mr.channel_identifier,
        c2.address,
        c1.address,
    ).call()

    log.info('channel data closer:', data=channel_data2)

    contract = web3.eth.contract(
        abi=contracts_manager.get_contract_abi(
            CONTRACT_MONITORING_SERVICE,
        ),
        address=monitoring_service.address
    )
    tx_hash = contract.functions.monitor(
        mr.signer,
        mr.non_closing_signer,
        mr.balance_hash,
        mr.nonce,
        mr.additional_hash,
        mr.closing_signature,
        mr.non_closing_signature,
        mr.reward_amount,
        mr.token_network_address,
        mr.reward_proof_signature,
    ).transact()
    # {'gas': 40_000} TODO: estimate gas better here
    log.info(f'Submit MR to SC, got tx_hash {encode_hex(tx_hash)}')
    assert tx_hash is not None
    data = web3.eth.waitForTransactionReceipt(tx_hash)
    log.info('MINED', tx=data)

    channel_data = network_contract.functions.getChannelParticipantInfo(
        mr.channel_identifier,
        c1.address,
        c2.address,
    ).call()

    log.info('channel data non-closer:', data=channel_data)
    channel_data2 = network_contract.functions.getChannelParticipantInfo(
        mr.channel_identifier,
        c2.address,
        c1.address,
    ).call()

    log.info('channel data closer:', data=channel_data2)


    gevent.sleep(1)
    wait_for_blocks(1)
    gevent.sleep(5)

    assert [e.event for e in blockchain_validator.events] == ['NewBalanceProofReceived']
    #
    # # wait for settle timeout
    # wait_for_blocks(15)
    # c2.settle_channel(
    #     c1.address,
    #     (balance_proof_c2.transferred_amount, balance_proof_c1.transferred_amount),
    #     (balance_proof_c2.locked_amount, balance_proof_c1.locked_amount),
    #     (balance_proof_c1.locksroot, balance_proof_c1.locksroot),
    # )
    # # Wait until the ChannelSettled is confirmed
    # wait_for_blocks(1)
    # # Let the MS claim its reward (for some reason this takes longer than TEST_POLL_INTERVAL)
    # gevent.sleep(0.1)
    # assert [e.event for e in blockchain_validator.events] == [
    #     'NewBalanceProofReceived', 'RewardClaimed',
    # ]
    #
    # final_balance = user_deposit_contract.functions.balances(
    #     monitoring_service.address,
    # ).call()
    # assert final_balance == (initial_balance + reward_amount)
