import pytest
from eth_utils import encode_hex, to_canonical_address
from raiden_common.utils.typing import Address
from web3.contract import Contract

from pathfinding_service.constants import MIN_IOU_EXPIRY
from pathfinding_service.model import IOU
from raiden_contracts.utils.proofs import sign_one_to_n_iou
from raiden_contracts.utils.type_aliases import ChainID, PrivateKey
from raiden_libs.utils import private_key_to_address, to_checksum_address
from tests.constants import TEST_CHAIN_ID


@pytest.fixture
def make_iou(one_to_n_contract: Contract):
    one_to_n_contract_address = to_canonical_address(one_to_n_contract.address)

    def f(
        sender_priv_key: PrivateKey,
        receiver: Address,
        amount=1,
        claimable_until=1000000000 * 15 + MIN_IOU_EXPIRY,
        one_to_n_address: Address = one_to_n_contract_address,
        chain_id: ChainID = ChainID(TEST_CHAIN_ID),
    ) -> IOU:
        receiver_hex: str = to_checksum_address(receiver)
        iou_dict = {
            "sender": to_checksum_address(private_key_to_address(sender_priv_key)),
            "receiver": receiver_hex,
            "amount": amount,
            "claimable_until": claimable_until,
            "one_to_n_address": to_checksum_address(one_to_n_address),
            "chain_id": chain_id,
        }
        iou_dict["signature"] = encode_hex(
            sign_one_to_n_iou(privatekey=sender_priv_key, **iou_dict)
        )
        iou = IOU.Schema().load(iou_dict)
        iou.claimed = False
        return iou

    return f
