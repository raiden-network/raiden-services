import os
from typing import List
from unittest.mock import Mock

from monitoring_service.events import ActionMonitoringTriggeredEvent
from monitoring_service.service import MonitoringService
from raiden.utils.typing import BlockNumber, ChannelID
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_contracts.tests.utils import get_random_address, get_random_privkey
from raiden_libs.events import ReceiveChannelOpenedEvent, UpdatedHeadBlockEvent
from raiden_libs.types import TokenNetworkAddress

from ...libs.mocks.web3 import ContractMock, Web3Mock


def test_crash(tmpdir, generate_raiden_clients, mockchain):
    """ Process blocks and compare results with/without crash

    A somewhat meaninful crash handling is simulated by not including the
    UpdatedHeadBlockEvent in every block.
    """
    channel_identifier = ChannelID(3)
    c1, c2 = generate_raiden_clients(2)
    token_network_address = TokenNetworkAddress(get_random_address())
    monitor_request = c2.get_monitor_request(
        balance_proof=c1.get_balance_proof(
            channel_id=channel_identifier,
            nonce=1,
            additional_hash="0x11",
            transferred_amount=2,
            locked_amount=0,
            locksroot="0x00",
        ),
        reward_amount=0,
    )

    events = [
        [
            ReceiveChannelOpenedEvent(
                token_network_address=token_network_address,
                channel_identifier=channel_identifier,
                participant1=c1.address,
                participant2=c2.address,
                settle_timeout=20,
                block_number=BlockNumber(0),
            )
        ],
        [UpdatedHeadBlockEvent(BlockNumber(1))],
        [
            ActionMonitoringTriggeredEvent(
                token_network_address=token_network_address,
                channel_identifier=channel_identifier,
                non_closing_participant=c2.address,
            )
        ],
        [UpdatedHeadBlockEvent(BlockNumber(3))],
    ]
    mockchain(events)

    server_private_key = get_random_privkey()

    contracts = {
        CONTRACT_TOKEN_NETWORK_REGISTRY: ContractMock(),
        CONTRACT_MONITORING_SERVICE: ContractMock(),
        CONTRACT_USER_DEPOSIT: ContractMock(),
    }

    def new_ms(filename):
        ms = MonitoringService(
            web3=Web3Mock(),
            private_key=server_private_key,
            contracts=contracts,
            db_filename=os.path.join(tmpdir, filename),
        )
        msc = Mock()
        ms.context.monitoring_service_contract = msc
        ms.monitor_mock = msc.functions.monitor.return_value.transact  # type: ignore
        ms.monitor_mock.return_value = bytes(0)  # type: ignore
        return ms

    # initialize both monitoring services
    stable_ms = new_ms("stable.db")
    crashy_ms = new_ms("crashy.db")
    for ms in [stable_ms, crashy_ms]:
        ms.database.conn.execute(
            "INSERT INTO token_network(address) VALUES (?)", [token_network_address]
        )
        ms.context.ms_state.blockchain_state.token_network_addresses = [token_network_address]
        ms.database.upsert_monitor_request(monitor_request)
        ms.database.conn.commit()

    # process each block and compare results between crashy and stable ms
    for to_block in range(len(events)):
        crashy_ms = new_ms("crashy.db")  # new instance to simulate crash
        stable_ms.monitor_mock.reset_mock()  # clear calls from last block
        result_state: List[dict] = []
        for ms in [stable_ms, crashy_ms]:
            ms._process_new_blocks(to_block)
            result_state.append(
                dict(
                    blockchain_state=ms.context.ms_state.blockchain_state,
                    db_dump=list(ms.database.conn.iterdump()),
                    monitor_calls=ms.monitor_mock.mock_calls,
                )
            )

        # both instances should have the same state after processing
        for stable_state, crashy_state in zip(result_state[0].values(), result_state[1].values()):
            # do asserts for each key separately to get better error messages
            assert stable_state == crashy_state
