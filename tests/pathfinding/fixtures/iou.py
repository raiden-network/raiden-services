import pytest
from eth_utils import encode_hex, to_canonical_address, to_checksum_address
from web3.contract import Contract

from pathfinding_service.constants import MIN_IOU_EXPIRY
from pathfinding_service.model import IOU
from raiden.utils.typing import Address
from raiden_contracts.utils.proofs import sign_one_to_n_iou
from raiden_contracts.utils.type_aliases import ChainID
from raiden_libs.utils import private_key_to_address


@pytest.fixture
def make_iou(one_to_n_contract: Contract):
    one_to_n_contract_address = to_canonical_address(one_to_n_contract.address)

    def f(
        sender_priv_key,
        receiver: Address,
        amount=1,
        expiration_block=MIN_IOU_EXPIRY + 100,
        one_to_n_address: Address = one_to_n_contract_address,
        chain_id: ChainID = ChainID(61),
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
