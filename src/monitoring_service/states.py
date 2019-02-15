from dataclasses import dataclass, field  # isort:skip noqa differences between python 3.6 and 3.7
from typing import Any, Dict, Iterable, List, Optional

import jsonschema
from eth_utils import decode_hex, encode_hex, to_checksum_address
from web3 import Web3

from raiden.utils.typing import (
    AdditionalHash,
    Address,
    BalanceHash,
    BlockNumber,
    ChainID,
    ChannelID,
    Nonce,
    Signature,
    TokenAmount,
    TokenNetworkAddress,
    TransactionHash,
)
from raiden_contracts.constants import ChannelState, MessageTypeId
from raiden_libs.messages.json_schema import MONITOR_REQUEST_SCHEMA
from raiden_libs.utils import eth_recover, eth_sign, pack_data


@dataclass
class OnChainUpdateStatus:
    update_sender_address: Address
    nonce: int


@dataclass
class Channel:
    token_network_address: TokenNetworkAddress
    identifier: ChannelID
    participant1: Address
    participant2: Address
    settle_timeout: int
    state: ChannelState = ChannelState.OPENED
    closing_block: Optional[BlockNumber] = None
    closing_participant: Optional[Address] = None

    closing_tx_hash: Optional[TransactionHash] = None
    claim_tx_hash: Optional[TransactionHash] = None

    update_status: Optional[OnChainUpdateStatus] = None

    @property
    def participants(self) -> Iterable[Address]:
        return (self.participant1, self.participant2)


@dataclass
class BlockchainState:
    chain_id: ChainID
    token_network_registry_address: Address
    monitor_contract_address: Address
    latest_known_block: BlockNumber
    token_network_addresses: List[TokenNetworkAddress] = field(default_factory=list)


@dataclass
class HashedBalanceProof:
    """ A hashed balance proof with signature """
    channel_identifier: ChannelID
    token_network_address: TokenNetworkAddress
    chain_id: ChainID

    balance_hash: BalanceHash
    nonce: Nonce
    additional_hash: AdditionalHash
    signature: Signature

    def __init__(
        self,
        channel_identifier: ChannelID,
        token_network_address: TokenNetworkAddress,
        chain_id: ChainID,
        nonce: Nonce,
        additional_hash: AdditionalHash,
        balance_hash: BalanceHash = None,
        signature: Signature = None,
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
    address: Address


@dataclass
class UnsignedMonitorRequest:
    # balance proof
    channel_identifier: ChannelID
    token_network_address: TokenNetworkAddress
    chain_id: ChainID

    balance_hash: BalanceHash
    nonce: Nonce
    additional_hash: AdditionalHash
    closing_signature: Signature

    # reward info
    reward_amount: TokenAmount

    # extracted from signature
    signer: Address = field(init=False)

    def __post_init__(self) -> None:
        self.signer = to_checksum_address(eth_recover(
            data=self.packed_balance_proof_data(),
            signature=decode_hex(self.closing_signature),
        ))

    @classmethod
    def from_balance_proof(
        cls,
        balance_proof: HashedBalanceProof,
        reward_amount: TokenAmount,
    ) -> 'UnsignedMonitorRequest':
        return cls(
            channel_identifier=balance_proof.channel_identifier,
            token_network_address=balance_proof.token_network_address,
            chain_id=balance_proof.chain_id,
            balance_hash=balance_proof.balance_hash,
            nonce=balance_proof.nonce,
            additional_hash=balance_proof.additional_hash,
            closing_signature=balance_proof.signature,
            reward_amount=reward_amount,
        )

    def sign(self, priv_key: str) -> 'MonitorRequest':
        return MonitorRequest(
            channel_identifier=self.channel_identifier,
            token_network_address=self.token_network_address,
            chain_id=self.chain_id,
            balance_hash=self.balance_hash,
            nonce=self.nonce,
            additional_hash=self.additional_hash,
            closing_signature=self.closing_signature,
            reward_amount=self.reward_amount,
            reward_proof_signature=encode_hex(
                eth_sign(priv_key, self.packed_reward_proof_data()),
            ),
            non_closing_signature=encode_hex(
                eth_sign(priv_key, self.packed_non_closing_data()),
            ),
        )

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


@dataclass
class MonitorRequest(UnsignedMonitorRequest):

    # signatures added by non_closing_signer
    non_closing_signature: Signature
    reward_proof_signature: Signature

    # extracted from signatures
    non_closing_signer: Address = field(init=False)
    reward_proof_signer: Address = field(init=False)

    def __post_init__(self) -> None:
        super(MonitorRequest, self).__post_init__()
        self.non_closing_signer = to_checksum_address(eth_recover(
            data=self.packed_non_closing_data(),
            signature=decode_hex(self.non_closing_signature),
        ))
        self.reward_proof_signer = to_checksum_address(eth_recover(
            data=self.packed_reward_proof_data(),
            signature=decode_hex(self.reward_proof_signature),
        ))

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
