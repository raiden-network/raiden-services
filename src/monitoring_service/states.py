from dataclasses import dataclass, field
from typing import Iterable, Optional

from eth_typing.evm import HexAddress
from eth_utils import decode_hex, encode_hex, to_checksum_address
from web3 import Web3

from raiden.constants import EMPTY_SIGNATURE
from raiden.messages.monitoring_service import RequestMonitoring, SignedBlindedBalanceProof
from raiden.utils.keys import privatekey_to_address
from raiden.utils.signer import LocalSigner, recover
from raiden.utils.typing import (
    AdditionalHash,
    Address,
    BalanceHash,
    BlockNumber,
    ChainID,
    ChannelID,
    MonitoringServiceAddress,
    Nonce,
    Signature,
    TokenAmount,
    TokenNetworkAddress,
    TransactionHash,
)
from raiden_contracts.constants import ChannelState, MessageTypeId
from raiden_contracts.utils.proofs import pack_balance_proof, pack_reward_proof
from raiden_contracts.utils.type_aliases import PrivateKey
from raiden_libs.states import BlockchainState


@dataclass
class OnChainUpdateStatus:
    update_sender_address: Address
    nonce: int


@dataclass
class Channel:
    # pylint: disable=too-many-instance-attributes
    token_network_address: TokenNetworkAddress
    identifier: ChannelID
    participant1: Address
    participant2: Address
    settle_timeout: int
    state: ChannelState = ChannelState.OPENED
    closing_block: Optional[BlockNumber] = None
    closing_participant: Optional[Address] = None

    monitor_tx_hash: Optional[TransactionHash] = None
    claim_tx_hash: Optional[TransactionHash] = None

    update_status: Optional[OnChainUpdateStatus] = None

    @property
    def participants(self) -> Iterable[Address]:
        return self.participant1, self.participant2


@dataclass(init=False)
class HashedBalanceProof:
    """A hashed balance proof with signature"""

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
        balance_hash: Optional[str] = None,
        signature: Optional[Signature] = None,
        # these three parameters can be passed instead of `balance_hash`
        transferred_amount: Optional[int] = None,
        locked_amount: Optional[int] = None,
        locksroot: Optional[str] = None,
        # can be used instead of passing `signature`
        priv_key: Optional[PrivateKey] = None,
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
                Web3.solidityKeccak(["uint256", "uint256", "bytes32"], balance_hash_data)
            )
        else:
            self.balance_hash = balance_hash

        if signature is None:
            assert priv_key
            local_signer = LocalSigner(private_key=priv_key)
            self.signature = local_signer.sign(self.serialize_bin())
        else:
            self.signature = signature

    def serialize_bin(self, msg_type: MessageTypeId = MessageTypeId.BALANCE_PROOF) -> bytes:
        return pack_balance_proof(
            to_checksum_address(self.token_network_address),
            self.chain_id,
            self.channel_identifier,
            BalanceHash(decode_hex(self.balance_hash)),
            self.nonce,
            AdditionalHash(decode_hex(self.additional_hash)),
            msg_type,
        )

    def get_request_monitoring(
        self,
        privkey: PrivateKey,
        reward_amount: TokenAmount,
        monitoring_service_contract_address: MonitoringServiceAddress,
    ) -> RequestMonitoring:
        """Returns raiden client's RequestMonitoring object"""
        non_closing_signer = LocalSigner(privkey)
        partner_signed_self = SignedBlindedBalanceProof(
            channel_identifier=self.channel_identifier,
            token_network_address=self.token_network_address,
            nonce=self.nonce,
            additional_hash=AdditionalHash(decode_hex(self.additional_hash)),
            chain_id=self.chain_id,
            signature=self.signature,
            balance_hash=BalanceHash(decode_hex(self.balance_hash)),
        )
        request_monitoring = RequestMonitoring(
            balance_proof=partner_signed_self,
            non_closing_participant=privatekey_to_address(privkey),
            reward_amount=reward_amount,
            signature=EMPTY_SIGNATURE,
            monitoring_service_contract_address=monitoring_service_contract_address,
        )
        request_monitoring.sign(non_closing_signer)
        return request_monitoring

    def get_monitor_request(
        self,
        privkey: PrivateKey,
        reward_amount: TokenAmount,
        msc_address: MonitoringServiceAddress,
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
            non_closing_participant=privatekey_to_address(privkey),
            msc_address=msc_address,
        ).sign(privkey)

    def get_counter_signature(self, privkey: PrivateKey) -> Signature:
        """Get a signature of this balance proof by the other party

        Useful for `closing_signature` of `TokenNetwork.closeChannel`
        """
        signer = LocalSigner(privkey)
        return signer.sign(self.serialize_bin() + self.signature)


@dataclass
class MonitoringServiceState:
    blockchain_state: BlockchainState
    address: Address


@dataclass
class UnsignedMonitorRequest:
    # pylint: disable=too-many-instance-attributes

    balance_hash: str
    nonce: Nonce
    additional_hash: str
    closing_signature: Signature

    # balance proof
    channel_identifier: ChannelID
    token_network_address: TokenNetworkAddress
    chain_id: ChainID

    # reward info
    msc_address: MonitoringServiceAddress
    reward_amount: TokenAmount
    non_closing_participant: Address

    # extracted from signature
    signer: Address = field(init=False)

    def __post_init__(self) -> None:
        self.signer = recover(
            data=self.packed_balance_proof_data(), signature=self.closing_signature
        )

    def sign(self, priv_key: PrivateKey) -> "MonitorRequest":
        local_signer = LocalSigner(private_key=priv_key)
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
            non_closing_participant=self.non_closing_participant,
            reward_proof_signature=local_signer.sign(
                self.packed_reward_proof_data(non_closing_signature)
            ),
            msc_address=self.msc_address,
        )

    def packed_balance_proof_data(
        self, message_type: MessageTypeId = MessageTypeId.BALANCE_PROOF
    ) -> bytes:
        return pack_balance_proof(
            to_checksum_address(self.token_network_address),
            self.chain_id,
            self.channel_identifier,
            BalanceHash(decode_hex(self.balance_hash)),
            self.nonce,
            AdditionalHash(decode_hex(self.additional_hash)),
            message_type,
        )

    def packed_reward_proof_data(self, non_closing_signature: Signature) -> bytes:
        """Return reward proof data serialized to binary"""
        return pack_reward_proof(
            monitoring_service_contract_address=to_checksum_address(self.msc_address),
            chain_id=self.chain_id,
            token_network_address=HexAddress(to_checksum_address(self.token_network_address)),
            non_closing_participant=HexAddress(to_checksum_address(self.non_closing_participant)),
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
        super().__post_init__()
        self.non_closing_signer = recover(
            data=self.packed_non_closing_data(), signature=self.non_closing_signature
        )
        self.reward_proof_signer = recover(
            data=self.packed_reward_proof_data(self.non_closing_signature),
            signature=self.reward_proof_signature,
        )
