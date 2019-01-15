import logging
import sys
import traceback
from typing import Dict, List

import gevent
from eth_utils import encode_hex, is_address, is_checksum_address, is_same_address
from web3 import Web3

from monitoring_service.exceptions import ServiceNotRegistered, StateDBInvalid
from monitoring_service.state_db import StateDBSqlite
from monitoring_service.tasks import OnChannelClose, OnChannelSettle
from monitoring_service.token_network_listener import TokenNetworkListener
from monitoring_service.utils import is_service_registered
from raiden_contracts.constants import CONTRACT_MONITORING_SERVICE, ChannelEvent
from raiden_contracts.contract_manager import ContractManager
from raiden_libs.gevent_error_handler import register_error_handler
from raiden_libs.messages import BalanceProof
from raiden_libs.private_contract import PrivateContract
from raiden_libs.types import Address
from raiden_libs.utils import is_channel_identifier, private_key_to_address

log = logging.getLogger(__name__)


def error_handler(context, exc_info):
    log.critical("Unhandled exception terminating the program")
    traceback.print_exception(
        etype=exc_info[0],
        value=exc_info[1],
        tb=exc_info[2],
    )
    sys.exit()


class MonitoringService(gevent.Greenlet):
    def __init__(
        self,
        web3: Web3,
        contract_manager: ContractManager,
        private_key: str,
        state_db: StateDBSqlite,
        registry_address: Address,
        monitor_contract_address: Address,
        sync_start_block: int = 0,
        required_confirmations: int = 8,
        poll_interval: int = 10,
    ):
        super().__init__()

        assert isinstance(private_key, str)
        assert is_checksum_address(private_key_to_address(private_key))

        self.web3 = web3
        self.contract_manager = contract_manager
        self.private_key = private_key
        self.state_db = state_db
        self.stop_event = gevent.event.Event()
        self.address = private_key_to_address(self.private_key)
        self.monitor_contract = PrivateContract(
            self.web3.eth.contract(
                abi=contract_manager.get_contract_abi(CONTRACT_MONITORING_SERVICE),
                address=monitor_contract_address,
            ),
        )

        self.token_network_listener = TokenNetworkListener(
            web3,
            contract_manager,
            registry_address,
            sync_start_block,
            required_confirmations,
            poll_interval,
            load_syncstate=state_db.load_syncstate,
            save_syncstate=state_db.save_syncstate,
            get_synced_contracts=state_db.get_synced_contracts,
        )
        self.token_network_listener.add_confirmed_channel_event_listener(
            self.on_channel_event,
        )

        # some sanity checks
        chain_id = int(self.web3.version.network)
        if state_db.is_initialized() is False:
            state_db.setup_db(chain_id, monitor_contract_address, self.address)
        if state_db.chain_id() != chain_id:
            raise StateDBInvalid("Chain id doesn't match!")
        if not is_same_address(state_db.server_address(), self.address):
            raise StateDBInvalid("Monitor service address doesn't match!")
        if not is_same_address(state_db.monitoring_contract_address(), monitor_contract_address):
            raise StateDBInvalid("Monitoring contract address doesn't match!")
        self.task_list: List[gevent.Greenlet] = []
        if not is_service_registered(
            self.web3,
            contract_manager,
            monitor_contract_address,
            self.address,
        ):
            raise ServiceNotRegistered(
                "Monitoring service %s is not registered in the Monitoring smart contract (%s)" %
                (self.address, monitor_contract_address),
            )

    def _run(self):
        register_error_handler(error_handler)
        self.token_network_listener.start()

        # this loop will wait until spawned greenlets complete
        while self.stop_event.is_set() is False:
            tasks = gevent.wait(self.task_list, timeout=5, count=1)
            if len(tasks) == 0:
                gevent.sleep(1)
                continue
            task = tasks[0]
            log.info('%s completed (%s)' % (task, task.value))
            self.task_list.remove(task)

    def stop(self):
        self.token_network_listener.stop()
        self.stop_event.set()

    def on_channel_event(self, event: Dict, tx: Dict):
        event_name = event['event']

        if event_name == ChannelEvent.OPENED:
            self.on_channel_open(event, tx)
        elif event_name == ChannelEvent.CLOSED:
            self.on_channel_close(event, tx)
        elif event_name == ChannelEvent.SETTLED:
            self.on_channel_settled(event, tx)
        else:
            log.info('Unhandled event: %s', event_name)

    def on_channel_open(self, event: Dict, tx: Dict):
        log.info('on channel open: event=%s tx=%s' % (event, tx))
        self.state_db.store_new_channel(
            channel_identifier=event['args']['channel_identifier'],
            token_network_address=event['address'],
            participant1=event['args']['participant1'],
            participant2=event['args']['participant2'],
        )

    def on_channel_close(self, event: Dict, tx: Dict):
        log.info('on channel close: event=%s tx=%s' % (event, tx))
        # check if we have balance proof for the closing
        closing_participant = event['args']['closing_participant']
        channel_id = event['args']['channel_identifier']
        tx_data = tx[1]
        tx_balance_proof = BalanceProof(
            channel_identifier=tx_data[0],
            token_network_address=event['address'],
            balance_hash=tx_data[1],
            nonce=tx_data[2],
            additional_hash=tx_data[3],
            chain_id=int(self.web3.version.network),
            signature=encode_hex(tx_data[4]),
        )
        assert tx_balance_proof is not None
        assert is_address(closing_participant)
        assert is_channel_identifier(channel_id)

        pkey_to_mr = self.state_db.get_monitor_requests(channel_id)
        for (_, non_closing_signer), monitor_request in pkey_to_mr.items():
            if non_closing_signer == closing_participant:
                # we don't have to act on behalf of the closing participant
                continue
            # submit monitor request
            self.start_task(
                OnChannelClose(self.monitor_contract, monitor_request, self.private_key),
            )

    def on_channel_settled(self, event: Dict, tx: Dict):
        channel_id = event['args']['channel_identifier']
        # TODO: only claim rewards if MS has submitted a BP.
        # See https://github.com/raiden-network/raiden-monitoring-service/issues/43
        for monitor_request in self.state_db.get_monitor_requests(channel_id).values():
            self.start_task(
                OnChannelSettle(monitor_request, self.monitor_contract, self.private_key),
            )

    def start_task(self, task: gevent.Greenlet):
        task.start()
        self.task_list.append(task)

    @property
    def monitor_requests(self):
        return self.state_db.get_monitor_requests()

    def wait_tasks(self):
        """Wait until all internal tasks are finished"""
        while True:
            if len(self.task_list) == 0:
                return
            gevent.sleep(1)
