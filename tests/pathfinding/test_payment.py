import pytest
from eth_utils import encode_hex

import pathfinding_service.exceptions as exceptions
from pathfinding_service.api import process_payment
from pathfinding_service.config import MIN_IOU_EXPIRY, UDC_SECURITY_MARGIN_FACTOR
from pathfinding_service.model import IOU
from raiden_contracts.tests.utils import get_random_address, get_random_privkey
from raiden_contracts.utils import sign_one_to_n_iou
from raiden_libs.utils import private_key_to_address


def make_iou(sender_priv_key, receiver, amount=1, expiration_block=MIN_IOU_EXPIRY + 100) -> dict:
    iou = {
        'sender': private_key_to_address(sender_priv_key),
        'receiver': receiver,
        'amount': amount,
        'expiration_block': expiration_block,
    }
    iou['signature'] = encode_hex(
        sign_one_to_n_iou(
            privatekey=sender_priv_key,
            sender=iou['sender'],
            receiver=receiver,
            amount=amount,
            expiration=expiration_block,
        )
    )
    return iou


def test_load_and_save_iou(pathfinding_service_mocked_listeners):
    pfs = pathfinding_service_mocked_listeners
    iou_dict = make_iou(get_random_privkey(), pfs.address)
    iou = IOU.Schema().load(iou_dict)[0]
    iou.claimed = False
    pfs.database.upsert_iou(iou)
    stored_iou = pfs.database.get_iou(iou.sender, iou.expiration_block)
    assert stored_iou == iou


def test_process_payment_errors(
    pathfinding_service_mocked_listeners, web3, deposit_to_udc, create_account, get_private_key
):
    pfs = pathfinding_service_mocked_listeners
    pfs.service_fee = 1
    sender = create_account()
    privkey = get_private_key(sender)

    # expires too early
    iou = make_iou(privkey, pfs.address, expiration_block=web3.eth.blockNumber + 5)
    with pytest.raises(exceptions.IOUExpiredTooEarly):
        process_payment(iou, pfs)

    # it fails it the no deposit is in the UDC
    iou = make_iou(privkey, pfs.address)
    with pytest.raises(exceptions.DepositTooLow):
        process_payment(iou, pfs)

    # must succeed if we add enough deposit to UDC
    deposit_to_udc(sender, 10)
    iou = make_iou(privkey, pfs.address)
    process_payment(iou, pfs)

    # malformed
    iou = make_iou(privkey, pfs.address)
    del iou['amount']
    with pytest.raises(exceptions.InvalidRequest):
        process_payment(iou, pfs)

    # wrong recipient
    iou = make_iou(privkey, get_random_address())
    with pytest.raises(exceptions.WrongIOURecipient):
        process_payment(iou, pfs)

    # bad signature
    iou = make_iou(privkey, pfs.address)
    iou['signature'] = hex(int(iou['signature'], 16) + 1)
    with pytest.raises(exceptions.InvalidSignature):
        process_payment(iou, pfs)

    # payment too low
    pfs.service_fee = 2
    iou = make_iou(privkey, pfs.address)
    with pytest.raises(exceptions.InsufficientServicePayment):
        process_payment(iou, pfs)


def test_process_payment(
    pathfinding_service_mocked_listeners, deposit_to_udc, create_account, get_private_key
):
    pfs = pathfinding_service_mocked_listeners
    pfs.service_fee = 1
    sender = create_account()
    privkey = get_private_key(sender)
    deposit_to_udc(sender, round(1 * UDC_SECURITY_MARGIN_FACTOR))

    # Make payment
    iou = make_iou(privkey, pfs.address, amount=1)
    process_payment(iou, pfs)

    # The same payment can't be reused
    with pytest.raises(exceptions.InsufficientServicePayment):
        process_payment(iou, pfs)

    # Increasing the amount would make the payment work again, if we had enough
    # deposit. But we set the deposit one token too low.
    deposit_to_udc(sender, round(2 * UDC_SECURITY_MARGIN_FACTOR) - 1)
    iou = make_iou(privkey, pfs.address, amount=2)
    with pytest.raises(exceptions.DepositTooLow):
        process_payment(iou, pfs)

    # With the higher amount and enough deposit, it works again!
    deposit_to_udc(sender, round(2 * UDC_SECURITY_MARGIN_FACTOR))
    iou = make_iou(privkey, pfs.address, amount=2)
    process_payment(iou, pfs)

    # Make sure the client does not create new sessions unnecessarily
    iou = make_iou(privkey, pfs.address, expiration_block=20000)
    with pytest.raises(exceptions.UseThisIOU):
        process_payment(iou, pfs)

    # Complain if the IOU has been claimed
    iou = make_iou(privkey, pfs.address, amount=3)
    pfs.database.conn.execute("UPDATE iou SET claimed=1")
    with pytest.raises(exceptions.IOUAlreadyClaimed):
        process_payment(iou, pfs)
