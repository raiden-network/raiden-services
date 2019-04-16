from typing import List
from unittest.mock import MagicMock, Mock

import pytest
from click.testing import CliRunner
from eth_utils import decode_hex

from pathfinding_service.claim_fees import claim_ious, get_claimable_ious, main
from pathfinding_service.model import IOU
from raiden.utils.signer import LocalSigner
from raiden.utils.typing import BlockNumber, Signature, TokenAmount


def test_claim_fees(
    pathfinding_service_mock,
    one_to_n_contract,
    web3,
    deposit_to_udc,
    get_accounts,
    get_private_key,
):
    # Prepare test data
    accounts = get_accounts(6)
    pfs = pathfinding_service_mock
    iou_inputs: List[dict] = [
        dict(sender=accounts[0], amount=100, deposit=200),
        dict(sender=accounts[1], amount=200, deposit=100),
        dict(sender=accounts[2], amount=102, deposit=0),  # insufficient deposit
        dict(sender=accounts[3], amount=103, deposit=99),  # insufficient deposit
        dict(sender=accounts[4], amount=104, claimed=True),  # already claimed
        dict(sender=accounts[4], amount=99),  # too low amount
        dict(sender=accounts[5], expiration_block=1000, amount=104),  # does not expire, yet
    ]

    # Create IOUs from `iou_inputs`
    ious: List[IOU] = []
    for iou_dict in iou_inputs:
        local_signer = LocalSigner(private_key=decode_hex(get_private_key(iou_dict['sender'])))
        iou = IOU(
            sender=iou_dict['sender'],
            receiver=pfs.address,
            amount=TokenAmount(iou_dict['amount']),
            expiration_block=BlockNumber(iou_dict.get('expiration_block', 100)),
            signature=Signature(bytes([1] * 64)),  # dummy, replaced below
            claimed=iou_dict.get('claimed', False),
        )
        iou.signature = Signature(local_signer.sign(iou.packed_data()))
        ious.append(iou)
        pfs.database.upsert_iou(iou)
        if iou_dict.get('deposit', 0) > 0:
            print(iou.sender, iou_dict['deposit'])
            deposit_to_udc(iou.sender, iou_dict['deposit'])

    # Check if the right IOUs are considered to be claimable
    expected_claimable = ious[:4]
    claimable_ious = list(
        get_claimable_ious(
            pfs.database, expires_before=BlockNumber(1000), claim_cost_rdn=TokenAmount(100)
        )
    )
    assert claimable_ious == expected_claimable

    # Claim IOUs
    skipped, failures = claim_ious(
        claimable_ious,
        claim_cost_rdn=TokenAmount(100),
        one_to_n_contract=one_to_n_contract,
        web3=web3,
        database=pfs.database,
    )
    assert (skipped, failures) == (2, 0)

    # Those IOUs which have enough deposit should be marked as claimed
    # * in the blockchain
    # * in the database
    # All other IOUs must not be changed.
    claimable_with_enough_deposit = ious[:2]
    for iou in ious:
        expected_claimed = iou in claimable_with_enough_deposit

        iou_in_db = pfs.database.get_iou(sender=iou.sender, expiration_block=iou.expiration_block)
        assert iou_in_db.claimed == expected_claimed

        is_settled = bool(one_to_n_contract.functions.settled_sessions(iou.session_id).call())
        assert is_settled == expected_claimed


@pytest.fixture
def mock_connect_to_blockchain(monkeypatch):
    web3_mock = Mock()
    web3_mock.net.version = 1
    web3_mock.eth.blockNumber = 1
    connect_mock = Mock(return_value=(web3_mock, MagicMock(), Mock()))
    monkeypatch.setattr('raiden_libs.cli.connect_to_blockchain', connect_mock)


@pytest.mark.usefixtures('mock_connect_to_blockchain')
def test_cli(default_cli_args):
    runner = CliRunner()
    result = runner.invoke(main, default_cli_args, catch_exceptions=False)
    assert result.exit_code == 0, result.output
