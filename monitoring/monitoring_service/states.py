from dataclasses import dataclass, field
from typing import List, Optional

from raiden_contracts.constants import ChannelState


@dataclass
class Channel:
    token_network_address: str
    identifier: int
    participant1: str
    participant2: str
    settle_timeout: int
    state: ChannelState = ChannelState.OPENED
    closing_block: Optional[int] = None


@dataclass
class MonitoringServiceState:
    token_network_registry_address: str
    monitor_contract_address: str
    latest_known_block: int
    token_network_addresses: List[str] = field(default_factory=list)


@dataclass
class MonitorRequest:
    # balance proof
    signature_prefix: str
    message_length: str
    token_network_address: str
    chain_id: int
    message_type_id: int
    channel_identifier: int
    balance_hash: bytes
    nonce: int
    additional_hash: bytes
    signature: bytes

    # reward infos
    non_closing_signature: bytes
    reward_amount: int
    reward_proof_signature: bytes

    @property
    def signer(self) -> str:
        # signer = eth_recover(
        #     data=self.serialize_bin(),
        #     signature=decode_hex(self.signature),
        # )
        # return to_checksum_address(signer)
        return ''  # FIXME: implement

    @property
    def non_closing_signer(self) -> str:
        # signer = eth_recover(
        #     data=self.non_closing_data,
        #     signature=decode_hex(self.non_closing_signature),
        # )
        # return to_checksum_address(signer)
        return ''  # FIXME: implement
