from dataclasses import dataclass, field
from typing import Iterable, Optional

from eth_utils import decode_hex, encode_hex, to_checksum_address
from web3 import Web3

from raiden.constants import EMPTY_SIGNATURE
from raiden.messages.monitoring_service import RequestMonitoring, SignedBlindedBalanceProof
from raiden.utils.signer import LocalSigner, recover
from raiden.utils.signing import pack_data
from raiden.utils.typing import (
    Address,
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
from raiden_contracts.utils.proofs import pack_reward_proof
from raiden_libs.states import BlockchainState


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
        return self.participant1, self.participant2


@dataclass(init=False)
class HashedBalanceProof:
    """ A hashed balance proof with signature """

    channel_identifier: ChannelID
    token_network_address: TokenNetworkAddress
    chain_id: ChainID

    balance_hash: str
    nonce: Nonce
    additional_hash: str
    signature: Signature

    def __init__(  # pylint: disable=too-many-arguments
        self,
        channel_identifier: ChannelID,
        token_network_address: TokenNetworkAddress,
        chain_id: ChainID,
        nonce: Nonce,
        additional_hash: str,
        balance_hash: str = None,
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
            self.balance_hash = encode_hex(
                Web3.soliditySha3(["uint256", "uint256", "bytes32"], balance_hash_data)
            )
        else:
            self.balance_hash = balance_hash

        if signature is None:
            assert priv_key
            local_signer = LocalSigner(private_key=decode_hex(priv_key))
            self.signature = local_signer.sign(self.serialize_bin())
        else:
            self.signature = signature

    def serialize_bin(self, msg_type: MessageTypeId = MessageTypeId.BALANCE_PROOF) -> bytes:
        return pack_data(
            (self.token_network_address, "address"),
            (self.chain_id, "uint256"),
            (msg_type.value, "uint256"),
            (self.channel_identifier, "uint256"),
            (decode_hex(self.balance_hash), "bytes32"),
            (self.nonce, "uint256"),
            (decode_hex(self.additional_hash), "bytes32"),
        )

    def get_request_monitoring(
        self,
        privkey: str,
        reward_amount: TokenAmount,
        monitoring_service_contract_address: Address,
    ) -> RequestMonitoring:
        """Returns raiden client's RequestMonitoring object"""
        non_closing_signer = LocalSigner(decode_hex(privkey))
        partner_signed_self = SignedBlindedBalanceProof(
            channel_identifier=self.channel_identifier,
            token_network_address=self.token_network_address,
            nonce=self.nonce,
            additional_hash=decode_hex(self.additional_hash),
            chain_id=self.chain_id,
            signature=self.signature,
            balance_hash=decode_hex(self.balance_hash),
        )
        request_monitoring = RequestMonitoring(
            balance_proof=partner_signed_self,
            reward_amount=reward_amount,
            signature=EMPTY_SIGNATURE,
            monitoring_service_contract_address=monitoring_service_contract_address,
        )
        request_monitoring.sign(non_closing_signer)
        return request_monitoring

    def get_monitor_request(
        self, privkey: str, reward_amount: TokenAmount, msc_address: Address
    ) -> "MonitorRequest":
        """Get monitor request message for a given balance proof."""
        return UnsignedMonitorRequest(
            channel_identifier=self.channel_identifier,
            token_network_address=self.token_network_address,
            chain_id=self.chain_id,
            balance_hash=self.balance_hash,
            nonce=self.nonce,
            additional_hash=self.additional_hash,
            closing_signature=self.signature,
            reward_amount=reward_amount,
            msc_address=msc_address,
        ).sign(privkey)

    def get_counter_signature(self, privkey: str) -> Signature:
        """Get a signature of this balance proof by the other party

        Useful for `closing_signature` of `TokenNetwork.closeChannel`
        """
        signer = LocalSigner(decode_hex(privkey))
        # TODO: use default message type id once
        #       https://github.com/raiden-network/raiden-contracts/issues/1149 is fixed
        return signer.sign(self.serialize_bin(MessageTypeId.BALANCE_PROOF_UPDATE) + self.signature)


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

    balance_hash: str
    nonce: Nonce
    additional_hash: str
    closing_signature: Signature

    # reward info
    msc_address: Address
    reward_amount: TokenAmount

    # extracted from signature
    signer: Address = field(init=False)

    def __post_init__(self) -> None:
        self.signer = recover(
            data=self.packed_balance_proof_data(), signature=self.closing_signature
        )

    @classmethod
    def from_balance_proof(
        cls, balance_proof: HashedBalanceProof, reward_amount: TokenAmount, msc_address: Address
    ) -> "UnsignedMonitorRequest":
        return cls(
            channel_identifier=balance_proof.channel_identifier,
            token_network_address=balance_proof.token_network_address,
            chain_id=balance_proof.chain_id,
            balance_hash=balance_proof.balance_hash,
            nonce=balance_proof.nonce,
            additional_hash=balance_proof.additional_hash,
            closing_signature=balance_proof.signature,
            reward_amount=reward_amount,
            msc_address=msc_address,
        )

    def sign(self, priv_key: str) -> "MonitorRequest":
        local_signer = LocalSigner(private_key=decode_hex(priv_key))
        non_closing_signature = local_signer.sign(self.packed_non_closing_data())
        return MonitorRequest(
            channel_identifier=self.channel_identifier,
            token_network_address=self.token_network_address,
            chain_id=self.chain_id,
            balance_hash=self.balance_hash,
            nonce=self.nonce,
            additional_hash=self.additional_hash,
            closing_signature=self.closing_signature,
            non_closing_signature=non_closing_signature,
            reward_amount=self.reward_amount,
            reward_proof_signature=local_signer.sign(
                self.packed_reward_proof_data(non_closing_signature)
            ),
            msc_address=self.msc_address,
        )

    def packed_balance_proof_data(
        self, message_type: MessageTypeId = MessageTypeId.BALANCE_PROOF
    ) -> bytes:
        return pack_data(
            (self.token_network_address, "address"),
            (self.chain_id, "uint256"),
            (message_type.value, "uint256"),
            (self.channel_identifier, "uint256"),
            (decode_hex(self.balance_hash), "bytes32"),
            (self.nonce, "uint256"),
            (decode_hex(self.additional_hash), "bytes32"),
        )

    def packed_reward_proof_data(self, non_closing_signature: Signature) -> bytes:
        """Return reward proof data serialized to binary"""
        return pack_reward_proof(
            monitoring_service_contract_address=to_checksum_address(self.msc_address),
            chain_id=self.chain_id,
            non_closing_signature=non_closing_signature,
            reward_amount=self.reward_amount,
        )

    def packed_non_closing_data(self) -> bytes:
        balance_proof = self.packed_balance_proof_data(
            message_type=MessageTypeId.BALANCE_PROOF_UPDATE
        )
        return balance_proof + self.closing_signature


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
        self.non_closing_signer = recover(
            data=self.packed_non_closing_data(), signature=self.non_closing_signature
        )
        self.reward_proof_signer = recover(
            data=self.packed_reward_proof_data(self.non_closing_signature),
            signature=self.reward_proof_signature,
        )
