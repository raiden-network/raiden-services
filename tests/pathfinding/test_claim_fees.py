from typing import List
from unittest.mock import MagicMock, Mock

import pytest
from click.testing import CliRunner
from eth_utils import decode_hex, to_canonical_address
from web3 import Web3

from pathfinding_service import metrics
from pathfinding_service.claim_fees import claim_ious, get_claimable_ious, main
from pathfinding_service.model import IOU
from pathfinding_service.service import PathfindingService
from raiden.utils.signer import LocalSigner
from raiden.utils.typing import ChainID, Signature, TokenAmount
from tests.libs.mocks.web3 import Web3Mock
from tests.utils import save_metrics_state


def test_metrics_iou(  # pylint: disable=too-many-locals
    pathfinding_service_web3_mock: PathfindingService,
    one_to_n_contract,
    web3: Web3,
    deposit_to_udc,
    get_accounts,
    get_private_key,
):
    pfs = pathfinding_service_web3_mock

    metrics_state = save_metrics_state(metrics.REGISTRY)
    # Prepare test data
    account = [decode_hex(acc) for acc in get_accounts(1)][0]
    local_signer = LocalSigner(private_key=get_private_key(account))
    iou = IOU(
        sender=account,
        receiver=pfs.address,
        amount=TokenAmount(100),
        claimable_until=web3.eth.get_block("latest").timestamp + 100,  # type: ignore
        signature=Signature(bytes([1] * 64)),
        chain_id=ChainID(61),
        one_to_n_address=to_canonical_address(one_to_n_contract.address),
        claimed=False,
    )
    iou.signature = Signature(local_signer.sign(iou.packed_data()))
    pfs.database.upsert_iou(iou)
    deposit_to_udc(iou.sender, 300)

    # Claim IOUs
    skipped, failures = claim_ious(
        ious=[iou],
        claim_cost_rdn=TokenAmount(100),
        one_to_n_contract=one_to_n_contract,
        web3=web3,
        database=pfs.database,
    )
    assert (skipped, failures) == (0, 0)

    assert (
        metrics_state.get_delta(
            "economics_iou_claims_total", labels=metrics.IouStatus.SUCCESSFUL.to_label_dict()
        )
        == 1.0
    )
    assert (
        metrics_state.get_delta(
            "economics_iou_claims_token_total",
            labels=metrics.IouStatus.SUCCESSFUL.to_label_dict(),
        )
        == 100.0
    )


def test_claim_fees(  # pylint: disable=too-many-locals
    pathfinding_service_web3_mock: PathfindingService,
    one_to_n_contract,
    web3: Web3,
    deposit_to_udc,
    get_accounts,
    get_private_key,
):
    pfs = pathfinding_service_web3_mock

    # Prepare test data
    accounts = [decode_hex(acc) for acc in get_accounts(7)]
    iou_inputs: List[dict] = [
        dict(sender=accounts[0], amount=100, deposit=200),
        dict(sender=accounts[1], amount=200, deposit=100),
        dict(sender=accounts[2], amount=102, deposit=0),  # insufficient deposit
        dict(sender=accounts[3], amount=103, deposit=99),  # insufficient deposit
        dict(sender=accounts[4], amount=104, claimed=True),  # already claimed
        dict(sender=accounts[4], amount=99),  # too low amount
        dict(sender=accounts[5], claimable_until=100 * 15, amount=104),  # does not expire, yet
        dict(
            sender=accounts[6],
            claimable_until=web3.eth.get_block(
                web3.eth.block_number - 1
            ).timestamp,  # type: ignore
            amount=104,
        ),  # already expired
    ]

    # Create IOUs from `iou_inputs`
    ious: List[IOU] = []
    for iou_dict in iou_inputs:
        local_signer = LocalSigner(private_key=get_private_key(iou_dict["sender"]))
        iou = IOU(
            sender=iou_dict["sender"],
            receiver=pfs.address,
            amount=TokenAmount(iou_dict["amount"]),
            claimable_until=iou_dict.get(
                "claimable_until", web3.eth.get_block("latest").timestamp + 100  # type: ignore
            ),
            signature=Signature(bytes([1] * 64)),  # dummy, replaced below
            chain_id=ChainID(61),
            one_to_n_address=to_canonical_address(one_to_n_contract.address),
            claimed=iou_dict.get("claimed", False),
        )
        iou.signature = Signature(local_signer.sign(iou.packed_data()))
        ious.append(iou)
        pfs.database.upsert_iou(iou)
        if iou_dict.get("deposit", 0) > 0:
            deposit_to_udc(iou.sender, iou_dict["deposit"])

    # Check if the right IOUs are considered to be claimable
    expected_claimable = ious[:4]
    timestamp_now = web3.eth.get_block("latest").timestamp  # type: ignore

    claimable_ious = list(
        get_claimable_ious(
            database=pfs.database,
            claimable_until_after=timestamp_now,
            claimable_until_before=timestamp_now + 10000,  # TODO: use proper boundaries
            claim_cost_rdn=TokenAmount(100),
        )
    )
    assert claimable_ious == expected_claimable

    # Claim IOUs
    skipped, failures = claim_ious(
        ious=claimable_ious,
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

        iou_in_db = pfs.database.get_iou(sender=iou.sender, claimable_until=iou.claimable_until)
        assert iou_in_db
        assert iou_in_db.claimed == expected_claimed

        is_settled = bool(one_to_n_contract.functions.settled_sessions(iou.session_id).call())
        assert is_settled == expected_claimed


@pytest.fixture
def mock_connect_to_blockchain(monkeypatch):
    web3_mock = Web3Mock()
    web3_mock.eth.generateGasPrice.return_value = int(1e9)
    connect_mock = Mock(return_value=(web3_mock, MagicMock(), 0))
    monkeypatch.setattr("raiden_libs.cli.connect_to_blockchain", connect_mock)


@pytest.mark.usefixtures("mock_connect_to_blockchain")
def test_cli(default_cli_args):
    default_cli_args.remove("--accept-disclaimer")
    runner = CliRunner()
    result = runner.invoke(main, default_cli_args, catch_exceptions=False)
    assert result.exit_code == 0, result.output
