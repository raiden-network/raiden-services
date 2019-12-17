import pytest
from eth_utils import encode_hex

from pathfinding_service.constants import MIN_IOU_EXPIRY
from pathfinding_service.model import IOU
from raiden.utils.formatting import to_checksum_address
from raiden.utils.typing import Address
from raiden_contracts.utils.proofs import sign_one_to_n_iou
from raiden_libs.utils import private_key_to_address


@pytest.fixture
def make_iou(one_to_n_contract):
    def f(
        sender_priv_key,
        receiver: Address,
        amount=1,
        expiration_block=MIN_IOU_EXPIRY + 100,
        one_to_n_address=one_to_n_contract.address,
        chain_id=1,
    ) -> IOU:
        receiver_hex: str = to_checksum_address(receiver)
        iou_dict = {
            "sender": to_checksum_address(private_key_to_address(sender_priv_key)),
            "receiver": receiver_hex,
            "amount": amount,
            "expiration_block": expiration_block,
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
