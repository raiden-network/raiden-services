from dataclasses import dataclass, field  # isort:skip noqa differences between python 3.6 and 3.7
from typing import List, Optional

from eth_utils import decode_hex, to_checksum_address

from raiden_contracts.constants import ChannelState, MessageTypeId
from raiden_libs.utils import eth_recover, pack_data


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

    closing_tx_hash: Optional[str] = None
    claim_tx_hash: Optional[str] = None

    update_status: Optional[OnChainUpdateStatus] = None


@dataclass
class BlockchainState:
    token_network_registry_address: str
    monitor_contract_address: str
    latest_known_block: int
    token_network_addresses: List[str] = field(default_factory=list)


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
