from unittest.mock import Mock, patch

from monitoring_service.service import MonitoringService
from raiden.tests.utils.factories import make_transaction_hash


def test_check_pending_transactions(web3, wait_for_blocks, monitoring_service: MonitoringService):
    required_confirmations = 3

    monitoring_service.context.required_confirmations = required_confirmations
    monitoring_service.database.add_waiting_transaction(waiting_tx_hash=make_transaction_hash())

    for tx_status in (0, 1):
        tx_receipt = {"blockNumber": web3.eth.blockNumber, "status": tx_status}
        with patch.object(web3.eth, "getTransactionReceipt", Mock(return_value=tx_receipt)):
            with patch.object(
                monitoring_service.database, "remove_waiting_transaction"
            ) as remove_mock:

                for should_call in (False, False, False, True):
                    monitoring_service.context.last_known_block = web3.eth.blockNumber
                    monitoring_service._check_pending_transactions()  # pylint: disable=protected-access # noqa

                    assert remove_mock.called == should_call
                    wait_for_blocks(1)
