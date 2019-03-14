import pytest

import pathfinding_service.exceptions as exceptions
from pathfinding_service.api.rest import process_payment
from pathfinding_service.model import IOU
from raiden_contracts.utils import sign_one_to_n_iou
from raiden_libs.utils import private_key_to_address


def make_iou(sender_priv_key, receiver, amount=1, expiration_block=10000) -> dict:
    iou = {
        'sender': private_key_to_address(sender_priv_key),
        'receiver': receiver,
        'amount': amount,
        'expiration_block': expiration_block,
    }
    iou['signature'] = sign_one_to_n_iou(
        privatekey=sender_priv_key,
        sender=iou['sender'],
        receiver=receiver,
        amount=amount,
        expiration=expiration_block,
    ).hex()
    return iou


def test_load_and_save_iou(
    pathfinding_service_mocked_listeners,
    get_random_privkey,
):
    pfs = pathfinding_service_mocked_listeners
    iou = IOU(**make_iou(get_random_privkey(), pfs.address))  # type: ignore
    iou.claimed = False
    pfs.database.upsert_iou(iou)
    stored_iou = pfs.database.get_iou(iou.sender, iou.expiration_block)
    assert stored_iou == iou


def test_process_payment_errors(
    pathfinding_service_mocked_listeners,
    get_random_privkey,
    get_random_address,
    web3,
):
    pfs = pathfinding_service_mocked_listeners
    pfs.service_fee = 1

    # first make sure that it usually doesn't raise errors
    iou = make_iou(get_random_privkey(), pfs.address)
    process_payment(iou, pfs)

    # malformed
    iou = make_iou(get_random_privkey(), pfs.address)
    del iou['amount']
    with pytest.raises(exceptions.InvalidRequest):
        process_payment(iou, pfs)

    # wrong recipient
    iou = make_iou(get_random_privkey(), get_random_address())
    with pytest.raises(exceptions.WrongIOURecipient):
        process_payment(iou, pfs)

    # expires too early
    iou = make_iou(get_random_privkey(), pfs.address, expiration_block=web3.eth.blockNumber + 5)
    with pytest.raises(exceptions.IOUExpiredTooEarly):
        process_payment(iou, pfs)

    # bad signature
    iou = make_iou(get_random_privkey(), pfs.address)
    iou['signature'] = hex(int(iou['signature'], 16) + 1)
    with pytest.raises(exceptions.InvalidIOUSignature):
        process_payment(iou, pfs)

    # payment too low
    pfs.service_fee = 2
    iou = make_iou(get_random_privkey(), pfs.address)
    with pytest.raises(exceptions.InsufficientServicePayment):
        process_payment(iou, pfs)


def test_process_payment(
    pathfinding_service_mocked_listeners,
    get_random_privkey,
):
    pfs = pathfinding_service_mocked_listeners
    pfs.service_fee = 1
    priv_key = get_random_privkey()
    iou = make_iou(priv_key, pfs.address, amount=1)
    process_payment(iou, pfs)

    # The same payment can't be reused
    with pytest.raises(exceptions.InsufficientServicePayment):
        process_payment(iou, pfs)

    # Increasing the amount makes the payment work again
    iou = make_iou(priv_key, pfs.address, amount=2)
    process_payment(iou, pfs)

    # Make sure the client does not create new sessions unnecessarily
    iou = make_iou(priv_key, pfs.address, expiration_block=20000)
    with pytest.raises(exceptions.UseThisIOU):
        process_payment(iou, pfs)

    # Complain if the IOU has been claimed
    iou = make_iou(priv_key, pfs.address, amount=3)
    pfs.database.conn.execute("UPDATE iou SET claimed=1")
    with pytest.raises(exceptions.IOUAlreadyClaimed):
        process_payment(iou, pfs)
