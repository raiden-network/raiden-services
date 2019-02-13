from dataclasses import dataclass, field  # isort:skip noqa differences between python 3.6 and 3.7
from typing import Any, Dict, List, Optional

import jsonschema
from eth_utils import decode_hex, encode_hex, to_checksum_address
from web3 import Web3

from raiden_contracts.constants import ChannelState, MessageTypeId
from raiden_libs.messages.json_schema import MONITOR_REQUEST_SCHEMA
from raiden_libs.utils import eth_recover, eth_sign, pack_data


@dataclass
class OnChainUpdateStatus:
    update_sender_address: str
    nonce: int


@dataclass
class Channel:
    token_network_address: str
    identifier: int
    participant1: str
    participant2: str
    settle_timeout: int
    state: ChannelState = ChannelState.OPENED
    closing_block: Optional[int] = None
    closing_participant: Optional[str] = None

    closing_tx_hash: Optional[str] = None
    claim_tx_hash: Optional[str] = None

    update_status: Optional[OnChainUpdateStatus] = None


@dataclass
class BlockchainState:
    chain_id: int
    token_network_registry_address: str
    monitor_contract_address: str
    latest_known_block: int
    token_network_addresses: List[str] = field(default_factory=list)


@dataclass
class HashedBalanceProof:
    """ A hashed balance proof with signature """
    channel_identifier: int
    token_network_address: str
    chain_id: int

    balance_hash: str
    nonce: int
    additional_hash: str
    signature: str

    def __init__(
        self,
        channel_identifier: int,
        token_network_address: str,
        chain_id: int,
        nonce: int,
        additional_hash: str,
        balance_hash: str = None,
        signature: str = None,
        # these three parameters can be passed instead of `balance_hash`
        transferred_amount: int = None,
        locked_amount: int = None,
        locksroot: str = None,
        # can be used instead of passing `signature`
        priv_key: str = None,
    ) -> None:
        self.channel_identifier = channel_identifier
        self.token_network_address = token_network_address
        self.chain_id = chain_id
        self.nonce = nonce
        self.additional_hash = additional_hash

        if balance_hash is None:
            assert signature is None
            balance_hash_data = (transferred_amount, locked_amount, locksroot)
            assert all(x is not None for x in balance_hash_data)
            self.balance_hash = encode_hex(Web3.soliditySha3(
                ['uint256', 'uint256', 'bytes32'],
                balance_hash_data,
            ))
        else:
            self.balance_hash = balance_hash

        if signature is None:
            assert priv_key
            self.signature = encode_hex(eth_sign(priv_key, self.serialize_bin()))
        else:
            self.signature = signature

    def serialize_bin(self, msg_type: MessageTypeId = MessageTypeId.BALANCE_PROOF) -> bytes:
        return pack_data([
            'address',
            'uint256',
            'uint256',
            'uint256',
            'bytes32',
            'uint256',
            'bytes32',
        ], [
            self.token_network_address,
            self.chain_id,
            msg_type.value,
            self.channel_identifier,
            decode_hex(self.balance_hash),
            self.nonce,
            decode_hex(self.additional_hash),
        ])


@dataclass
class MonitoringServiceState:
    blockchain_state: BlockchainState
    address: str


@dataclass
class MonitorRequest:
    # balance proof
    channel_identifier: int
    token_network_address: str
    chain_id: int

    balance_hash: str
    nonce: int
    additional_hash: str
    closing_signature: str

    # reward infos
    non_closing_signature: str
    reward_amount: int
    reward_proof_signature: str

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'MonitorRequest':
        jsonschema.validate(data, MONITOR_REQUEST_SCHEMA)
        result = cls(
            data['balance_proof']['channel_identifier'],
            data['balance_proof']['token_network_address'],
            data['balance_proof']['chain_id'],
            data['balance_proof']['balance_hash'],
            data['balance_proof']['nonce'],
            data['balance_proof']['additional_hash'],
            data['balance_proof']['closing_signature'],
            data['non_closing_signature'],
            data['reward_proof_signature'],
            data['reward_amount'],
        )
        return result

    def packed_balance_proof_data(
        self,
        message_type: MessageTypeId = MessageTypeId.BALANCE_PROOF,
    ) -> bytes:
        return pack_data([
            'address',
            'uint256',
            'uint256',
            'uint256',
            'bytes32',
            'uint256',
            'bytes32',
        ], [
            self.token_network_address,
            self.chain_id,
            message_type.value,
            self.channel_identifier,
            decode_hex(self.balance_hash),
            self.nonce,
            decode_hex(self.additional_hash),
        ])

    def packed_reward_proof_data(self) -> bytes:
        """Return reward proof data serialized to binary"""
        return pack_data([
            'uint256',
            'uint256',
            'address',
            'uint256',
            'uint256',
        ], [
            self.channel_identifier,
            self.reward_amount,
            self.token_network_address,
            self.chain_id,
            self.nonce,
        ])

    def packed_non_closing_data(self) -> bytes:
        balance_proof = self.packed_balance_proof_data(
            message_type=MessageTypeId.BALANCE_PROOF_UPDATE,
        )
        return balance_proof + decode_hex(self.closing_signature)

    @property
    def signer(self) -> str:
        signer = eth_recover(
            data=self.packed_balance_proof_data(),
            signature=decode_hex(self.closing_signature),
        )
        return to_checksum_address(signer)

    @property
    def non_closing_signer(self) -> str:
        signer = eth_recover(
            data=self.packed_non_closing_data(),
            signature=decode_hex(self.non_closing_signature),
        )
        return to_checksum_address(signer)

    @property
    def reward_proof_signer(self) -> str:
        signer = eth_recover(
            data=self.packed_reward_proof_data(),
            signature=decode_hex(self.reward_proof_signature),
        )
        return to_checksum_address(signer)
