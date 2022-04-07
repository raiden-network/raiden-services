import sys
from typing import Dict, Iterable, Tuple

import click
import structlog
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import TransactionNotFound
from web3.gas_strategies.rpc import rpc_gas_price_strategy

from pathfinding_service.database import PFSDatabase
from pathfinding_service.model import IOU
from raiden.utils.typing import BlockNumber, Timestamp
from raiden_contracts.constants import CONTRACT_ONE_TO_N
from raiden_contracts.contract_manager import gas_measurements
from raiden_contracts.utils.type_aliases import ChainID, TokenAmount
from raiden_libs.cli import blockchain_options, common_options
from raiden_libs.utils import get_posix_utc_time_now, private_key_to_address

log = structlog.get_logger(__name__)

GAS_COST_SAFETY_MARGIN = 1.1


@blockchain_options(contracts=[CONTRACT_ONE_TO_N])
@click.command()
@click.option(
    "--rdn-per-eth",
    default=0.0025,
    type=float,
    help="Current RDN/ETH price, used to check claimed amount > transaction cost",
)
@click.option(
    "--expire-within",
    default=60 * 60 * 24 * 7,  # one week
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
    expire_within: Timestamp,
) -> None:
    pfs_address = private_key_to_address(private_key)
    chain_id = ChainID(web3.eth.chain_id)
    database = PFSDatabase(
        filename=state_db, chain_id=chain_id, pfs_address=pfs_address, sync_start_block=start_block
    )

    claim_cost_rdn = calc_claim_cost_rdn(web3, rdn_per_eth)
    time_now = get_posix_utc_time_now()
    ious = list(
        get_claimable_ious(
            database,
            claimable_until_after=time_now,
            claimable_until_before=Timestamp(time_now + expire_within),
            claim_cost_rdn=claim_cost_rdn,
        )
    )
    print(f"Found {len(ious)} claimable IOUs")
    _, failures = claim_ious(ious, claim_cost_rdn, contracts[CONTRACT_ONE_TO_N], web3, database)
    if failures:
        sys.exit(1)


def calc_claim_cost_rdn(web3: Web3, rdn_per_eth: float) -> TokenAmount:
    web3.eth.setGasPriceStrategy(rpc_gas_price_strategy)
    claim_cost_gas = gas_measurements()["OneToN.claim"]

    gas_price = web3.eth.generateGasPrice()
    assert gas_price is not None, "Could not generate gas price"

    claim_cost_eth = claim_cost_gas * gas_price * GAS_COST_SAFETY_MARGIN
    return TokenAmount(int(claim_cost_eth / rdn_per_eth))


def get_claimable_ious(
    database: PFSDatabase,
    claimable_until_after: Timestamp,
    claimable_until_before: Timestamp,
    claim_cost_rdn: TokenAmount,
) -> Iterable[IOU]:
    return database.get_ious(
        claimed=False,
        claimable_until_after=claimable_until_after,
        claimable_until_before=claimable_until_before,
        amount_at_least=claim_cost_rdn,
    )


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
            claimable_until=iou.claimable_until,
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
        for tx_hash, iou in unchecked_txs.copy():
            try:
                receipt = web3.eth.get_transaction_receipt(tx_hash)
            except TransactionNotFound:
                continue

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
