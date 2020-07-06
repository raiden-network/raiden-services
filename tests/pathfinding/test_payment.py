import pytest
from eth_utils import decode_hex, to_canonical_address

from pathfinding_service import exceptions
from pathfinding_service.api import process_payment
from raiden.utils.typing import Address, TokenAmount
from raiden_contracts.tests.utils import get_random_privkey
from raiden_libs.constants import UDC_SECURITY_MARGIN_FACTOR_PFS


def test_save_and_load_iou(pathfinding_service_mock, make_iou):
    pfs = pathfinding_service_mock
    iou = make_iou(decode_hex(get_random_privkey()), pfs.address)
    pfs.database.upsert_iou(iou)
    stored_iou = pfs.database.get_iou(iou.sender, iou.expiration_block)
    assert stored_iou == iou


def test_process_payment_errors(
    pathfinding_service_web3_mock,
    web3,
    deposit_to_udc,
    create_account,
    get_private_key,
    make_iou,
    one_to_n_contract,
):
    pfs = pathfinding_service_web3_mock
    sender = create_account()
    privkey = get_private_key(sender)

    def test_payment(iou, service_fee=TokenAmount(1)):
        process_payment(
            iou=iou,
            pathfinding_service=pfs,
            service_fee=service_fee,
            one_to_n_address=to_canonical_address(one_to_n_contract.address),
        )

    # expires too early
    iou = make_iou(privkey, pfs.address, expiration_block=web3.eth.blockNumber + 5)
    with pytest.raises(exceptions.IOUExpiredTooEarly):
        test_payment(iou)

    # it fails it the no deposit is in the UDC
    iou = make_iou(privkey, pfs.address)
    with pytest.raises(exceptions.DepositTooLow):
        test_payment(iou)

    # adding deposit does not help immediately
    deposit_to_udc(sender, 10)
    with pytest.raises(exceptions.DepositTooLow):
        test_payment(iou)

    # must succeed after deposit is confirmed
    web3.testing.mine(pathfinding_service_web3_mock.required_confirmations)
    test_payment(iou)

    # wrong recipient
    iou = make_iou(privkey, Address(bytes([6] * 20)))
    with pytest.raises(exceptions.WrongIOURecipient):
        test_payment(iou)

    # wrong chain_id
    iou = make_iou(privkey, pfs.address, chain_id=2)
    with pytest.raises(exceptions.UnsupportedChainID):
        test_payment(iou)

    # wrong one_to_n_address
    iou = make_iou(privkey, pfs.address, one_to_n_address=bytes([1] * 20))
    with pytest.raises(exceptions.WrongOneToNAddress):
        test_payment(iou)

    # payment too low
    iou = make_iou(privkey, pfs.address)
    with pytest.raises(exceptions.InsufficientServicePayment):
        test_payment(iou, service_fee=TokenAmount(2))


def test_process_payment(
    pathfinding_service_web3_mock,
    deposit_to_udc,
    create_account,
    get_private_key,
    make_iou,
    one_to_n_contract,
    web3,
):
    pfs = pathfinding_service_web3_mock
    service_fee = TokenAmount(1)
    sender = create_account()
    privkey = get_private_key(sender)
    deposit_to_udc(sender, round(1 * UDC_SECURITY_MARGIN_FACTOR_PFS))
    web3.testing.mine(pathfinding_service_web3_mock.required_confirmations)
    one_to_n_address = to_canonical_address(one_to_n_contract.address)

    # Make payment
    iou = make_iou(privkey, pfs.address, amount=1)
    process_payment(iou, pfs, service_fee, one_to_n_address)

    # The same payment can't be reused
    with pytest.raises(exceptions.InsufficientServicePayment):
        process_payment(iou, pfs, service_fee, one_to_n_address)

    # Increasing the amount would make the payment work again, if we had enough
    # deposit. But we set the deposit one token too low.
    deposit_to_udc(sender, round(2 * UDC_SECURITY_MARGIN_FACTOR_PFS) - 1)
    iou = make_iou(privkey, pfs.address, amount=2)
    with pytest.raises(exceptions.DepositTooLow) as tb:
        process_payment(iou, pfs, service_fee, one_to_n_address)
    assert tb.value.error_details["required_deposit"] == 2 * UDC_SECURITY_MARGIN_FACTOR_PFS
    assert tb.value.error_details["seen_deposit"] == 1 * UDC_SECURITY_MARGIN_FACTOR_PFS
    assert tb.value.error_details["block_number"] == web3.eth.blockNumber

    # With the higher amount and enough deposit, it works again!
    deposit_to_udc(sender, round(2 * UDC_SECURITY_MARGIN_FACTOR_PFS))
    web3.testing.mine(pathfinding_service_web3_mock.required_confirmations)
    iou = make_iou(privkey, pfs.address, amount=2)
    process_payment(iou, pfs, service_fee, one_to_n_address)

    # Make sure the client does not create new sessions unnecessarily
    iou = make_iou(privkey, pfs.address, expiration_block=20000)
    with pytest.raises(exceptions.UseThisIOU):
        process_payment(iou, pfs, service_fee, one_to_n_address)

    # Complain if the IOU has been claimed
    iou = make_iou(privkey, pfs.address, amount=3)
    pfs.database.conn.execute("UPDATE iou SET claimed=1")
    with pytest.raises(exceptions.IOUAlreadyClaimed):
        process_payment(iou, pfs, service_fee, one_to_n_address)
