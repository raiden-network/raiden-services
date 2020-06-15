"""
The test in this module uses the mocked raiden client to create blockchain events and
processes them. Additionally, it mocks the transport layer directly. It tests the
interaction of many moving parts - yet, it is currently really slow.
Therefore, usually mocked_integration should be used.
"""
from typing import List
from unittest.mock import Mock, patch

from eth_utils import decode_hex, encode_hex, to_canonical_address

from monitoring_service.states import HashedBalanceProof
from pathfinding_service.constants import DEFAULT_REVEAL_TIMEOUT
from pathfinding_service.model import ChannelView
from pathfinding_service.service import PathfindingService
from raiden.utils.typing import BlockNumber, BlockTimeout, ChainID, Nonce, TokenNetworkAddress
from raiden_contracts.constants import (
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
    LOCKSROOT_OF_NO_LOCKS,
    TEST_SETTLE_TIMEOUT_MIN,
)
from raiden_contracts.utils.type_aliases import PrivateKey


def test_pfs_with_mocked_client(  # pylint: disable=too-many-arguments
    web3,
    token_network_registry_contract,
    channel_descriptions_case_1: List,
    get_accounts,
    user_deposit_contract,
    token_network,
    custom_token,
    create_channel,
    get_private_key,
):  # pylint: disable=too-many-locals
    """ Instantiates some MockClients and the PathfindingService.

    Mocks blockchain events to setup a token network with a given topology, specified in
    the channel_description fixture. Tests all PFS methods w.r.t. to that topology
    """
    clients = get_accounts(7)
    token_network_address = TokenNetworkAddress(to_canonical_address(token_network.address))

    with patch("pathfinding_service.service.MatrixListener", new=Mock):
        pfs = PathfindingService(
            web3=web3,
            contracts={
                CONTRACT_TOKEN_NETWORK_REGISTRY: token_network_registry_contract,
                CONTRACT_USER_DEPOSIT: user_deposit_contract,
            },
            required_confirmations=BlockTimeout(1),
            db_filename=":memory:",
            poll_interval=0.1,
            sync_start_block=BlockNumber(0),
            private_key=PrivateKey(
                decode_hex("3a1076bf45ab87712ad64ccb3b10217737f7faacbf2872e88fdd9a537d8fe266")
            ),
        )

    # greenlet needs to be started and context switched to
    pfs.start()
    pfs.updated.wait(timeout=5)

    # there should be one token network registered
    assert len(pfs.token_networks) == 1

    token_network_model = pfs.token_networks[token_network_address]
    graph = token_network_model.G
    channel_identifiers = []
    for (
        p1_index,
        p1_capacity,
        _p1_fee,
        _p1_reveal_timeout,
        _p1_reachability,
        p2_index,
        p2_capacity,
        _p2_fee,
        _p2_reveal_timeout,
        _p2_reachability,
        _settle_timeout,
    ) in channel_descriptions_case_1:
        # order is important here because we check order later
        channel_id = create_channel(clients[p1_index], clients[p2_index])[0]
        channel_identifiers.append(channel_id)

        for address, partner_address, amount in [
            (clients[p1_index], clients[p2_index], p1_capacity),
            (clients[p2_index], clients[p1_index], p2_capacity),
        ]:
            custom_token.functions.mint(amount).transact({"from": address})
            custom_token.functions.approve(token_network.address, amount).transact(
                {"from": address}
            )
            token_network.functions.setTotalDeposit(
                channel_id, address, amount, partner_address
            ).transact({"from": address})

    web3.testing.mine(1)  # 1 confirmation block
    pfs.updated.wait(timeout=5)

    # there should be as many open channels as described
    assert len(token_network_model.channel_id_to_addresses.keys()) == len(
        channel_descriptions_case_1
    )

    # check that deposits, settle_timeout and transfers got registered
    for index in range(len(channel_descriptions_case_1)):
        channel_identifier = channel_identifiers[index]
        p1_address, p2_address = token_network_model.channel_id_to_addresses[channel_identifier]
        view1: ChannelView = graph[p1_address][p2_address]["view"]
        view2: ChannelView = graph[p2_address][p1_address]["view"]
        assert view1.settle_timeout == TEST_SETTLE_TIMEOUT_MIN
        assert view2.settle_timeout == TEST_SETTLE_TIMEOUT_MIN
        assert view1.reveal_timeout == DEFAULT_REVEAL_TIMEOUT
        assert view2.reveal_timeout == DEFAULT_REVEAL_TIMEOUT

    # now close all channels
    for (
        index,
        (
            p1_index,
            _p1_capacity,
            _p1_fee,
            _p1_reveal_timeout,
            _p1_reachability,
            p2_index,
            _p2_capacity,
            _p2_fee,
            _p2_reveal_timeout,
            _p2_reachability,
            _settle_timeout,
        ),
    ) in enumerate(channel_descriptions_case_1):
        channel_id = channel_identifiers[index]
        balance_proof = HashedBalanceProof(
            nonce=Nonce(1),
            transferred_amount=0,
            priv_key=get_private_key(clients[p2_index]),
            channel_identifier=channel_id,
            token_network_address=TokenNetworkAddress(to_canonical_address(token_network.address)),
            chain_id=ChainID(61),
            additional_hash="0x%064x" % 0,
            locked_amount=0,
            locksroot=encode_hex(LOCKSROOT_OF_NO_LOCKS),
        )
        token_network.functions.closeChannel(
            channel_id,
            clients[p2_index],
            clients[p1_index],
            balance_proof.balance_hash,
            balance_proof.nonce,
            balance_proof.additional_hash,
            balance_proof.signature,
            balance_proof.get_counter_signature(get_private_key(clients[p1_index])),
        ).transact({"from": clients[p1_index], "gas": 200_000})

    web3.testing.mine(1)  # 1 confirmation block
    pfs.updated.wait(timeout=5)

    # there should be no channels
    assert len(token_network_model.channel_id_to_addresses.keys()) == 0
    pfs.stop()
