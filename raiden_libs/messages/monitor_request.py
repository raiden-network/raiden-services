from raiden_libs.messages.message import Message
from raiden_libs.messages.balance_proof import BalanceProof
from raiden_libs.properties import address_property
from eth_utils import is_address, to_checksum_address, decode_hex
from raiden_libs.messages.json_schema import MONITOR_REQUEST_SCHEMA
from raiden_libs.utils import UINT64_MAX, UINT192_MAX, UINT256_MAX
import struct
import jsonschema


class MonitorRequest(Message):
    """Message sent by a Raiden node to the MS. It cointains all data required to
    call MSC
    """
    reward_sender_address = address_property('_reward_sender_address')  # type: ignore
    token_network_address = address_property('_token_network_address')  # type: ignore
    monitor_address = address_property('_monitor_address')  # type: ignore
    _type = 'MonitorRequest'

    def __init__(
        self,
        channel_identifier: int,        # uint256
        nonce: int,                     # uint64
        transferred_amount: int,        # uint256
        locksroot: str = None,               # str -> bytes 32
        extra_hash: bytes = None,         # bytes 32
        signature: bytes = None,          # bytes
        reward_sender_address: bytes = None,   # address
        reward_proof_signature: bytes = None,  # bytes
        reward_amount: int = None,             # uint192
        token_network_address: str = None,     # address
        chain_id: int = None,                  # uint256 (ethereum chain id)
        monitor_address: str = None
    ) -> None:
        # TODO: how does server know which chain should be used?
        assert (channel_identifier > 0) and (channel_identifier <= UINT256_MAX)
        assert (nonce >= 1) and (nonce < UINT64_MAX)
        assert (transferred_amount >= 0) and (transferred_amount <= UINT256_MAX)
        assert (reward_amount >= 0) and (reward_amount <= UINT192_MAX)
        assert len(decode_hex(locksroot)) == 32
        assert len(decode_hex(extra_hash)) == 32
        assert signature is None or len(decode_hex(signature)) == 65
        assert is_address(reward_sender_address)
        assert is_address(token_network_address)
        assert is_address(monitor_address)
        assert chain_id > 0

        self.channel_identifier = channel_identifier
        self.nonce = nonce
        self.transferred_amount = transferred_amount
        self.locksroot = locksroot
        self.extra_hash = extra_hash
        self.balance_proof_signature = signature
        self.reward_sender_address = to_checksum_address(reward_sender_address)
        self.reward_proof_signature = reward_proof_signature
        self.token_network_address = to_checksum_address(token_network_address)
        self.reward_amount = reward_amount
        self.chain_id = chain_id
        self.monitor_address = monitor_address

    def serialize_data(self):
        msg = self.__dict__.copy()
        msg['reward_sender_address'] = msg.pop('_reward_sender_address')
        msg['token_network_address'] = msg.pop('_token_network_address')
        msg['monitor_address'] = msg.pop('_monitor_address')
        return msg

    def serialize_reward_proof(self):
        """Return reward proof data serialized to binary"""
        order = '>32s24s20s32s8s20s'
        return struct.pack(
            order,
            self.channel_identifier.to_bytes(32, byteorder='big'),
            self.reward_amount.to_bytes(24, byteorder='big'),
            decode_hex(self.token_network_address),
            self.chain_id.to_bytes(32, byteorder='big'),
            self.nonce.to_bytes(8, byteorder='big'),
            decode_hex(self.monitor_address)
        )

    @classmethod
    def deserialize(cls, data):
        jsonschema.validate(data, MONITOR_REQUEST_SCHEMA)
        ret = cls(
            data['channel_identifier'],
            data['nonce'],
            data['transferred_amount'],
            data['locksroot'],
            data['extra_hash'],
            data['balance_proof_signature'],
            data['reward_sender_address'],
            data['reward_proof_signature'],
            data['reward_amount'],
            data['token_network_address'],
            data['chain_id'],
            data['monitor_address']
        )
        return ret

    def get_balance_proof(self):
        return BalanceProof(
            self.channel_identifier,
            self.token_network_address,
            self.nonce,
            self.locksroot,
            self.transferred_amount,
            self.extra_hash,
            self.chain_id,
            self.balance_proof_signature
        )
