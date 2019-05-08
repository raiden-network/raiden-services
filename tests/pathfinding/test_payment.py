import pytest
from eth_utils import encode_hex, to_checksum_address

import pathfinding_service.exceptions as exceptions
from pathfinding_service.api import process_payment
from pathfinding_service.config import MIN_IOU_EXPIRY, UDC_SECURITY_MARGIN_FACTOR
from pathfinding_service.model import IOU
from raiden.utils.typing import Address, TokenAmount
from raiden_contracts.tests.utils import get_random_privkey
from raiden_contracts.utils import sign_one_to_n_iou
from raiden_libs.utils import private_key_to_address


def make_iou(
    sender_priv_key, receiver: Address, amount=1, expiration_block=MIN_IOU_EXPIRY + 100
) -> IOU:
    receiver_hex: str = to_checksum_address(receiver)
    iou_dict = {
        "sender": to_checksum_address(private_key_to_address(sender_priv_key)),
        "receiver": receiver_hex,
        "amount": amount,
        "expiration_block": expiration_block,
    }
    iou_dict["signature"] = encode_hex(
        sign_one_to_n_iou(
            privatekey=sender_priv_key,
            sender=iou_dict["sender"],
            receiver=receiver_hex,
            amount=amount,
            expiration=expiration_block,
        )
    )
    iou = IOU.Schema(strict=True).load(iou_dict)[0]
    iou.claimed = False
    return iou


def test_save_and_load_iou(pathfinding_service_mock):
    pfs = pathfinding_service_mock
    iou = make_iou(get_random_privkey(), pfs.address)
    pfs.database.upsert_iou(iou)
    stored_iou = pfs.database.get_iou(iou.sender, iou.expiration_block)
    assert stored_iou == iou


def test_process_payment_errors(
    pathfinding_service_web3_mock, web3, deposit_to_udc, create_account, get_private_key
):
    pfs = pathfinding_service_web3_mock
    sender = create_account()
    privkey = get_private_key(sender)

    # expires too early
    iou = make_iou(privkey, pfs.address, expiration_block=web3.eth.blockNumber + 5)
    with pytest.raises(exceptions.IOUExpiredTooEarly):
        process_payment(iou, pfs, service_fee=TokenAmount(1))

    # it fails it the no deposit is in the UDC
    iou = make_iou(privkey, pfs.address)
    with pytest.raises(exceptions.DepositTooLow):
        process_payment(iou, pfs, service_fee=TokenAmount(1))

    # must succeed if we add enough deposit to UDC
    deposit_to_udc(sender, 10)
    process_payment(iou, pfs, service_fee=TokenAmount(1))

    # wrong recipient
    iou = make_iou(privkey, Address(bytes([6] * 20)))
    with pytest.raises(exceptions.WrongIOURecipient):
        process_payment(iou, pfs, service_fee=TokenAmount(1))

    # payment too low
    iou = make_iou(privkey, pfs.address)
    with pytest.raises(exceptions.InsufficientServicePayment):
        process_payment(iou, pfs, service_fee=TokenAmount(2))


def test_process_payment(
    pathfinding_service_web3_mock, deposit_to_udc, create_account, get_private_key
):
    pfs = pathfinding_service_web3_mock
    service_fee = TokenAmount(1)
    sender = create_account()
    privkey = get_private_key(sender)
    deposit_to_udc(sender, round(1 * UDC_SECURITY_MARGIN_FACTOR))

    # Make payment
    iou = make_iou(privkey, pfs.address, amount=1)
    process_payment(iou, pfs, service_fee)

    # The same payment can't be reused
    with pytest.raises(exceptions.InsufficientServicePayment):
        process_payment(iou, pfs, service_fee)

    # Increasing the amount would make the payment work again, if we had enough
    # deposit. But we set the deposit one token too low.
    deposit_to_udc(sender, round(2 * UDC_SECURITY_MARGIN_FACTOR) - 1)
    iou = make_iou(privkey, pfs.address, amount=2)
    with pytest.raises(exceptions.DepositTooLow):
        process_payment(iou, pfs, service_fee)

    # With the higher amount and enough deposit, it works again!
    deposit_to_udc(sender, round(2 * UDC_SECURITY_MARGIN_FACTOR))
    iou = make_iou(privkey, pfs.address, amount=2)
    process_payment(iou, pfs, service_fee)

    # Make sure the client does not create new sessions unnecessarily
    iou = make_iou(privkey, pfs.address, expiration_block=20000)
    with pytest.raises(exceptions.UseThisIOU):
        process_payment(iou, pfs, service_fee)

    # Complain if the IOU has been claimed
    iou = make_iou(privkey, pfs.address, amount=3)
    pfs.database.conn.execute("UPDATE iou SET claimed=1")
    with pytest.raises(exceptions.IOUAlreadyClaimed):
        process_payment(iou, pfs, service_fee)
