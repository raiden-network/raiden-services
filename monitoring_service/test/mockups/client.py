from eth_utils import is_checksum_address, remove_0x_prefix, is_same_address, encode_hex
from coincurve import PrivateKey
from functools import wraps
from sha3 import keccak_256
from web3.utils.events import get_event_data
from web3 import Web3
import logging

from raiden_contracts.contract_manager import get_event_from_abi

from raiden_libs.utils import private_key_to_address, make_filter
from monitoring_service.messages import BalanceProof


log = logging.getLogger(__name__)
NULL_ADDRESS = '0x0000000000000000000000000000000000000000'


def get_event_logs(
    web3: Web3,
    contract_abi: dict,
    event_name: str,
    fromBlock=0,
    toBlock=None
):
    """Helper function to get all event logs in a given range"""
    abi = get_event_from_abi(contract_abi, event_name)
    tmp_filter = make_filter(web3, abi, fromBlock=0, toBlock=toBlock)
    entries = tmp_filter.get_all_entries()
    web3.eth.uninstallFilter(tmp_filter.filter_id)
    return entries


def sha3(data):
    return keccak_256(data).digest()


def assert_channel_existence(func):
    @wraps(func)
    def func_wrapper(self, partner_address, *args, **kwargs):
        assert is_checksum_address(partner_address)
        assert partner_address in self.partner_to_channel_id
        return func(self, partner_address, *args, **kwargs)
    return func_wrapper


def sync_channels(func):
    @wraps(func)
    def func_wrapper(self, *args, **kwargs):
        self.partner_to_channel_id = self.sync_open_channels()
        return func(self, *args, **kwargs)
    return func_wrapper


class MockRaidenNode:
    def __init__(self, privkey, channel_contract):
        self.privkey = privkey
        self.address = private_key_to_address(privkey)
        self.contract = channel_contract
        self.partner_to_channel_id = dict()
        self.token_network_abi = None
        self.token_contract = None
        self.client_registry = dict()
        self.web3 = self.contract.web3

    @sync_channels
    def open_channel(self, partner_address):
        assert is_checksum_address(partner_address)
        assert partner_address in self.client_registry
        # disallow multiple open channels with a same partner
        if partner_address in self.partner_to_channel_id:
            return self.partner_to_channel_id[partner_address]
        # if it doesn't exist, register new channel
        txid = self.contract.transact({'from': self.address}).openChannel(
            self.address,
            partner_address,
            15
        )
        assert txid is not None
        tx = self.web3.eth.getTransactionReceipt(txid)
        assert tx is not None
        assert len(tx['logs']) == 1
        event = get_event_data(
            get_event_from_abi(self.contract.abi, 'ChannelOpened'),
            tx['logs'][0]
        )

        channel_id = event['args']['channel_identifier']
        assert channel_id > 0
        assert (is_same_address(event['args']['participant1'], self.address) or
                is_same_address(event['args']['participant2'], self.address))
        assert (is_same_address(event['args']['participant1'], partner_address) or
                is_same_address(event['args']['participant2'], partner_address))

        self.partner_to_channel_id[partner_address] = channel_id
        self.client_registry[partner_address].open_channel(self.address)

        return channel_id

    def get_my_address(self, address1, address2):
        if is_same_address(self.address, address1):
            return address1
        if is_same_address(self.address, address2):
            return address2
        assert False

    def get_other_address(self, address1, address2):
        if is_same_address(self.address, address1):
            return address2
        if is_same_address(self.address, address2):
            return address1
        assert False

    def sync_open_channels(self):
        """Parse logs and update internal channel state to include all already open channels"""
        entries = get_event_logs(self.web3, self.contract.abi, 'ChannelOpened')
        open_channels = {
            self.get_other_address(
                x['args']['participant1'],
                x['args']['participant2']
            ): x['args']['channel_identifier']
            for x in entries
            if self.address in (
                x['args']['participant1'],
                x['args']['participant2']
            )
        }
        # remove already closed channels from the list
        entries = get_event_logs(self.web3, self.contract.abi, 'ChannelClosed')
        closed_channels = [
            x['args']['channel_identifier']
            for x in entries
            if x['args']['channel_identifier'] in open_channels.keys()
        ]
        return {
            k: v
            for k, v in open_channels.items()
            if k not in closed_channels
        }

    @assert_channel_existence
    def deposit_to_channel(self, partner_address, amount):
        channel_id = self.partner_to_channel_id[partner_address]
        self.token_contract.transact(
            {'from': self.address}
        ).approve(self.contract.address, amount)
        return self.contract.transact(
            {'from': self.address}
        ).setDeposit(
            channel_id,
            partner_address,
            amount
        )

    @assert_channel_existence
    def close_channel(self, partner_address, balance_proof):
        assert balance_proof is not None
        channel_id = self.partner_to_channel_id[partner_address]
        self.contract.transact({'from': self.address}).closeChannel(
            channel_id,
            balance_proof.nonce,
            balance_proof.transferred_amount,
            balance_proof.locksroot,
            balance_proof.extra_hash,
            balance_proof.signature
        )

    @assert_channel_existence
    def settle_channel(self, partner_address):
        channel_id = self.partner_to_channel_id[partner_address]
        self.contract.transact({'from': self.address}).settleChannel(
            channel_id,
            self.address,
            partner_address
        )

    @assert_channel_existence
    def get_balance_proof(self, partner_address, **kwargs):
        channel_id = self.partner_to_channel_id[partner_address]
        bp = BalanceProof(
            channel_id,
            self.contract.address,
            self.address,
            partner_address,
            **kwargs
        )
        bp.signature = encode_hex(self.sign_data(bp.serialize_bin(), self.privkey))
        return bp

    @assert_channel_existence
    def update_transfer(self, partner_address, balance_proof):
        channel_id = self.partner_to_channel_id[partner_address]
        self.contract.transact({'from': self.address}).updateTransfer(
            channel_id,
            balance_proof.nonce,
            balance_proof.transferred_amount,
            balance_proof.locksroot,
            balance_proof.extra_hash,
            balance_proof.signature
        )

    @staticmethod
    def sign_data(data, privkey):
        pk = PrivateKey.from_hex(remove_0x_prefix(privkey))
        sig = pk.sign_recoverable(data, hasher=sha3)
        return sig[:-1] + chr(sig[-1] + 27).encode()
