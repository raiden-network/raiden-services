import jsonschema
from eth_utils import decode_hex, is_address, to_checksum_address

from raiden_contracts.constants import MessageTypeId
from raiden_libs.messages.balance_proof import BalanceProof
from raiden_libs.messages.json_schema import MONITOR_REQUEST_SCHEMA
from raiden_libs.messages.message import Message
from raiden_libs.properties import address_property
from raiden_libs.types import Address
from raiden_libs.utils import UINT192_MAX, eth_recover, pack_data


class MonitorRequest(Message):
    """Message sent by a Raiden node to the MS. It cointains all data required to
    call MSC
    """
    _type = 'MonitorRequest'

    def __init__(
        self,
        balance_proof: BalanceProof,
        non_closing_signature: str = None,
        reward_proof_signature: bytes = None,  # bytes
        reward_amount: int = None,             # uint192
    ) -> None:
        assert non_closing_signature is None or len(decode_hex(non_closing_signature)) == 65
        assert reward_amount is None or (reward_amount >= 0) and (reward_amount <= UINT192_MAX)
        # todo: validate reward proof signature
        assert isinstance(balance_proof, BalanceProof)

        self._balance_proof = balance_proof
        self.non_closing_signature = non_closing_signature
        self.reward_proof_signature = reward_proof_signature
        self.reward_amount = reward_amount

    def serialize_data(self):
        msg = self.__dict__.copy()
        msg.pop('_balance_proof')
        msg['balance_proof'] = self.balance_proof.serialize_data()
        msg['reward_proof_signature'] = self.reward_proof_signature
        return msg

    def serialize_reward_proof(self):
        """Return reward proof data serialized to binary"""
        return pack_data([
            'uint256',
            'uint256',
            'address',
            'uint256',
            'uint256',
        ], [
            self.balance_proof.channel_identifier,
            self.reward_amount,
            self.balance_proof.token_network_address,
            self.balance_proof.chain_id,
            self.balance_proof.nonce,
        ])

    @classmethod
    def deserialize(cls, data):
        jsonschema.validate(data, MONITOR_REQUEST_SCHEMA)
        balance_proof = BalanceProof.deserialize(data['balance_proof'])
        result = cls(
            balance_proof,
            data['non_closing_signature'],
            data['reward_proof_signature'],
            data['reward_amount'],
        )
        return result

    @property
    def balance_proof(self):
        return self._balance_proof

    @property
    def reward_proof_signer(self) -> str:
        signer = eth_recover(
            data=self.serialize_reward_proof(),
            signature=decode_hex(self.reward_proof_signature),
        )
        return to_checksum_address(signer)

    @property
    def non_closing_data(self) -> bytes:
        serialized = self.balance_proof.serialize_bin(msg_type=MessageTypeId.BALANCE_PROOF_UPDATE)
        return serialized + decode_hex(self.balance_proof.signature)

    @property
    def non_closing_signer(self) -> str:
        signer = eth_recover(
            data=self.non_closing_data,
            signature=decode_hex(self.non_closing_signature),
        )
        return to_checksum_address(signer)
