import logging
from typing import Dict
from functools import wraps

from eth_utils import is_checksum_address, is_same_address, encode_hex, decode_hex
from web3.utils.events import get_event_data
from web3 import Web3
from web3.contract import Contract

from raiden_contracts.contract_manager import get_event_from_abi

from raiden_libs.utils import private_key_to_address, make_filter, sign_data
from raiden_libs.messages import BalanceProof, MonitorRequest, FeeInfo
from raiden_libs.types import Address, ChannelIdentifier


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


def assert_channel_existence(func):
    """Trigger an assert if there is no channel registered with an other participant"""
    @wraps(func)
    def func_wrapper(self, partner_address, *args, **kwargs):
        assert is_checksum_address(partner_address)
        assert partner_address in self.partner_to_channel_id
        return func(self, partner_address, *args, **kwargs)
    return func_wrapper


def sync_channels(func):
    """Synchronize all channels opened with a client"""
    @wraps(func)
    def func_wrapper(self, *args, **kwargs):
        self.partner_to_channel_id = self.sync_open_channels()
        return func(self, *args, **kwargs)
    return func_wrapper


class MockRaidenNode:
    def __init__(
        self,
        privkey: str,
        token_network_contract: Contract,
        token_contract: Contract
    ) -> None:
        self.privkey = privkey
        self.address = private_key_to_address(privkey)
        self.contract = token_network_contract
        self.token_contract = token_contract
        self.partner_to_channel_id: Dict[Address, ChannelIdentifier] = dict()
        self.token_network_abi = None
        self.client_registry: Dict[Address, 'MockRaidenNode'] = dict()
        self.web3 = self.contract.web3

    @sync_channels
    def open_channel(self, partner_address: Address) -> int:
        """Opens channel with a single partner
        Parameters:
            partner_address - a valid ethereum address of the partner
        Return:
            channel_id - id of the channel
        """
        assert is_checksum_address(partner_address)
        assert partner_address in self.client_registry
        # disallow multiple open channels with a same partner
        if partner_address in self.partner_to_channel_id:
            return self.partner_to_channel_id[partner_address]
        # if it doesn't exist, register new channel
        txid = self.contract.functions.openChannel(
            self.address,
            partner_address,
            15
        ).transact({'from': self.address})
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

    # TODO: maybe change this to a single function that orders the pair
    #   so this node address is first and partner address second
    def get_my_address(self, address1: Address, address2: Address) -> Address:
        """Pick an address that is equal to address of this MockRaidenNode"""
        if is_same_address(self.address, address1):
            return address1
        if is_same_address(self.address, address2):
            return address2
        assert False

    def get_other_address(self, address1: Address, address2: Address) -> Address:
        """Pick an address that is not equal to address of this MockRaidenNode"""
        if is_same_address(self.address, address1):
            return address2
        if is_same_address(self.address, address2):
            return address1
        assert False

    def sync_open_channels(self) -> Dict[Address, Dict]:
        """Parses logs and update internal channel state to include all already open channels."""
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
    def deposit_to_channel(self, partner_address: Address, amount: int) -> str:
        """Deposits specified amount to an open channel
        Parameters:
            partner_address - address of a partner the client has open channel with
            amount - amount to deposit
        Return:
            transaction hash of the transaction calling `TokenNetwork::setDeposit()` method
        """
        channel_info = self.get_own_channel_info(partner_address)
        channel_id = self.partner_to_channel_id[partner_address]
        self.token_contract.functions.approve(
            self.contract.address,
            amount
        ).transact({'from': self.address})
        return self.contract.functions.setDeposit(
            channel_id,
            self.address,
            amount + channel_info['deposit']
        ).transact({'from': self.address})

    @assert_channel_existence
    def close_channel(self, partner_address: Address, balance_proof: BalanceProof):
        """Closes an open channel"""
        assert balance_proof is not None
        channel_id = self.partner_to_channel_id[partner_address]
        self.contract.functions.closeChannel(
            channel_id,
            balance_proof.balance_hash,
            balance_proof.nonce,
            balance_proof.additional_hash,
            balance_proof.signature
        ).transact({'from': self.address})

    @assert_channel_existence
    def settle_channel(
        self,
        partner_address: Address,
        transferred=tuple(),
        locked=tuple(),
        locksroot=tuple()
    ):
        """Settles a closed channel. Settling requires that the challenge period is over"""
        assert len(transferred) == 2
        assert len(locked) == 2
        assert len(locksroot) == 2
        channel_id = self.partner_to_channel_id[partner_address]
        self.contract.functions.settleChannel(
            channel_id,
            self.address,
            transferred[0],
            locked[0],
            locksroot[0],
            partner_address,
            transferred[1],
            locked[1],
            locksroot[1]
        ).transact({'from': self.address})

    @assert_channel_existence
    def get_balance_proof(self, partner_address: Address, **kwargs) -> BalanceProof:
        """Get a signed balance proof for an open channel.
        Parameters:
            partner_address - address of a partner the node has channel open with
            **kwargs - arguments to BalanceProof constructor
        """
        channel_id = self.partner_to_channel_id[partner_address]
        bp = BalanceProof(
            channel_id,
            self.contract.address,
            **kwargs
        )
        bp.signature = encode_hex(sign_data(self.privkey, bp.serialize_bin()))
        return bp

    @assert_channel_existence
    def get_monitor_request(
        self,
        partner_address: Address,
        balance_proof: BalanceProof,
        reward_amount: int,
        monitor_address: Address
    ) -> MonitorRequest:
        """Get monitor request message for a given balance proof."""
        monitor_request = MonitorRequest(
            balance_proof,
            reward_sender_address=self.address,
            reward_proof_signature=None,
            reward_amount=reward_amount,
            monitor_address=monitor_address
        )
        monitor_request.reward_proof_signature = encode_hex(
            sign_data(
                self.privkey,
                monitor_request.serialize_reward_proof()
            )
        )
        non_closing_data = balance_proof.serialize_bin() + decode_hex(balance_proof.signature)
        monitor_request.non_closing_signature = encode_hex(
            sign_data(self.privkey, non_closing_data)
        )
        return monitor_request

    @assert_channel_existence
    def get_fee_info(self, partner_address: Address, **kwargs) -> FeeInfo:
        """Get a signed fee info message for an open channel.
        Parameters:
            partner_address - address of a partner the node has channel open with
            **kwargs - arguments to FeeInfo constructor
        """
        channel_id = self.partner_to_channel_id[partner_address]
        fi = FeeInfo(
            self.contract.address,
            channel_id,
            **kwargs
        )
        fi.signature = encode_hex(sign_data(self.privkey, fi.serialize_bin()))
        return fi

    @assert_channel_existence
    def update_transfer(self, partner_address: Address, balance_proof: BalanceProof):
        """Given a valid signed balance proof, this method calls `updateTransfer`
        for an open channel
        """
        channel_id = self.partner_to_channel_id[partner_address]
        non_closing_data = balance_proof.serialize_bin() + decode_hex(balance_proof.signature)
        non_closing_signature = encode_hex(sign_data(self.privkey, non_closing_data))
        self.contract.functions.updateNonClosingBalanceProof(
            channel_id,
            balance_proof.balance_hash,
            balance_proof.nonce,
            balance_proof.additional_hash,
            balance_proof.signature,
            non_closing_signature
        ).transact({'from': self.address})

    @assert_channel_existence
    def get_partner_channel_info(self, partner_address: Address) -> Dict:
        """Return a state of partner's side of the channel, serialized as a dict"""
        channel_identifier = self.partner_to_channel_id[partner_address]
        return self.get_channel_participant_info(channel_identifier, partner_address, self.address)

    @assert_channel_existence
    def get_own_channel_info(self, partner_address: Address) -> Dict:
        """Return a state of our own side of the channel, serialized as a dict"""
        channel_identifier = self.partner_to_channel_id[partner_address]
        return self.get_channel_participant_info(channel_identifier, self.address, partner_address)

    def get_channel_participant_info(
        self,
        channel_identifier: ChannelIdentifier,
        participant_address: Address,
        partner_address: Address
    ):
        channel_info = self.contract.functions.getChannelParticipantInfo(
            channel_identifier,
            participant_address,
            partner_address
        ).call()
        return_fields = [
            'deposit',
            'initialized',
            'is_closer',
            'balance_hash_or_locksroot',
            'nonce_or_locked_amount'
        ]
        assert len(return_fields) == len(channel_info)
        return {
            field: channel_info[return_fields.index(field)]
            for field in return_fields
        }
