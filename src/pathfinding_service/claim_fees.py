import sys
from typing import Dict, Iterable, Tuple

import click
import structlog
from web3 import Web3
from web3.contract import Contract

from pathfinding_service.database import PFSDatabase
from pathfinding_service.model import IOU
from raiden.utils.typing import BlockNumber, ChainID, TokenAmount
from raiden_contracts.constants import CONTRACT_ONE_TO_N
from raiden_libs.cli import blockchain_options, common_options
from raiden_libs.utils import private_key_to_address

log = structlog.get_logger(__name__)


@blockchain_options(contracts=[CONTRACT_ONE_TO_N])
@click.command()
@click.option(
    "--rdn-per-eth",
    default=0.0025,
    type=float,
    help="Current RDN/ETH price, used to check claimed amount > transaction cost",
)
@click.option(
    "--expires-within",
    default=4 * 60 * 24 * 7,  # one week
    type=click.IntRange(min=1),
    help="Only IOUs which expire withing this number of blocks will be claimed",
)
@common_options("raiden-pathfinding-service")
def main(
    private_key: str,
    state_db: str,
    web3: Web3,
    contracts: Dict[str, Contract],
    start_block: BlockNumber,
    rdn_per_eth: float,
    expires_within: BlockNumber,
) -> None:
    pfs_address = private_key_to_address(private_key)
    chain_id = ChainID(int(web3.net.version))
    database = PFSDatabase(
        filename=state_db, chain_id=chain_id, pfs_address=pfs_address, sync_start_block=start_block
    )

    claim_cost_eth = 90897
    claim_cost_rdn = TokenAmount(int(claim_cost_eth / rdn_per_eth))
    ious = list(
        get_claimable_ious(
            database,
            expires_before=web3.eth.blockNumber + expires_within,
            claim_cost_rdn=claim_cost_rdn,
        )
    )
    print(f"Found {len(ious)} claimable IOUs")
    _, failures = claim_ious(ious, claim_cost_rdn, contracts[CONTRACT_ONE_TO_N], web3, database)
    if failures:
        sys.exit(1)


def get_claimable_ious(
    database: PFSDatabase, expires_before: BlockNumber, claim_cost_rdn: TokenAmount
) -> Iterable[IOU]:
    ious = database.get_ious(
        claimed=False, expires_before=expires_before, amount_at_least=claim_cost_rdn
    )
    return ious


def claim_ious(
    ious: Iterable[IOU],
    claim_cost_rdn: TokenAmount,
    one_to_n_contract: Contract,
    web3: Web3,
    database: PFSDatabase,
) -> Tuple[int, int]:
    unchecked_txs = []
    skipped = 0
    for iou in ious:
        claim = one_to_n_contract.functions.claim(
            sender=iou.sender,
            receiver=iou.receiver,
            amount=iou.amount,
            expiration_block=iou.expiration_block,
            one_to_n_address=iou.one_to_n_address,
            signature=iou.signature,
        )
        transferrable = claim.call()
        if transferrable < claim_cost_rdn:
            print("Not enough user deposit to claim profitably for", iou)
            skipped += 1
            continue
        tx_hash = claim.transact()
        unchecked_txs.append((tx_hash, iou))

    failures = 0
    while unchecked_txs:
        for tx_hash, iou in unchecked_txs:
            receipt = web3.eth.getTransactionReceipt(tx_hash)
            if receipt is not None:
                unchecked_txs.remove((tx_hash, iou))
                if receipt["status"] == 1:
                    print(f"Successfully claimed {iou}.")
                    iou.claimed = True
                    database.upsert_iou(iou)
                else:
                    print(f"Claiming {iou} failed!")
                    failures += 1

    return skipped, failures


if __name__ == "__main__":
    main(auto_envvar_prefix="PFS")  # pragma: no cover
