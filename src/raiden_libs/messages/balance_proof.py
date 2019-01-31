import jsonschema
from eth_utils import decode_hex, encode_hex, is_address, to_checksum_address
from web3 import Web3

from raiden_contracts.constants import MessageTypeId
from raiden_libs.messages.json_schema import BALANCE_PROOF_SCHEMA
from raiden_libs.messages.message import Message
from raiden_libs.properties import address_property
from raiden_libs.types import Address, ChannelIdentifier, T_ChannelIdentifier
from raiden_libs.utils import UINT256_MAX, eth_recover, pack_data


class BalanceProof(Message):
    """ A Balance Proof

    If transferred_amount, locked_amount and locksroot are set, balance_proof hash is
    computed using these values. Otherwise a value stored in _balance_hash is returned.

    Serialization will also add these items only if each of transferred_amount, locked_amount
    and locksroot is set.
    """
    def __init__(
        self,
        channel_identifier: ChannelIdentifier,
        token_network_address: Address,

        balance_hash: str = None,
        nonce: int = 0,
        additional_hash: str = '0x%064x' % 0,
        chain_id: int = 1,
        signature: str = None,

        transferred_amount: int = None,
        locked_amount: int = 0,
        locksroot: str = '0x%064x' % 0,
    ) -> None:
        super().__init__()
        assert isinstance(channel_identifier, T_ChannelIdentifier)
        assert is_address(token_network_address)

        self._type = 'BalanceProof'

        self.channel_identifier = channel_identifier
        self.token_network_address = token_network_address

        self._balance_hash = balance_hash
        self.additional_hash = additional_hash
        self.nonce = nonce
        self.chain_id = chain_id
        self.signature = signature

        if transferred_amount and locked_amount and locksroot and balance_hash:
            assert 0 <= transferred_amount <= UINT256_MAX
            assert 0 <= locked_amount <= UINT256_MAX
            assert self.hash_balance_data(
                transferred_amount,
                locked_amount,
                locksroot,
            ) == balance_hash

        self.transferred_amount = transferred_amount
        self.locked_amount = locked_amount
        self.locksroot = locksroot

    def serialize_data(self) -> dict:
        result = {
            'channel_identifier': self.channel_identifier,
            'token_network_address': self.token_network_address,

            'balance_hash': self.balance_hash,
            'additional_hash': self.additional_hash,
            'nonce': self.nonce,
            'chain_id': self.chain_id,
            'signature': self.signature,
        }

        if None not in (self.transferred_amount, self.locked_amount, self.locksroot):
            result['transferred_amount'] = self.transferred_amount
            result['locked_amount'] = self.locked_amount
            result['locksroot'] = self.locksroot

        return result

    def serialize_bin(self, msg_type: MessageTypeId = MessageTypeId.BALANCE_PROOF):
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

    @classmethod
    def deserialize(cls, data):
        jsonschema.validate(data, BALANCE_PROOF_SCHEMA)
        result = cls(
            data['channel_identifier'],
            data['token_network_address'],
            balance_hash=data['balance_hash'],
            nonce=data['nonce'],
            additional_hash=data['additional_hash'],
            chain_id=data['chain_id'],
            signature=data['signature'],

            transferred_amount=data.get('transferred_amount', None),
            locked_amount=data.get('locked_amount', None),
            locksroot=data.get('locksroot', None),
        )
        return result

    token_network_address = address_property('_contract')  # type: ignore
    json_schema = BALANCE_PROOF_SCHEMA

    @property
    def balance_hash(self) -> str:
        if self._balance_hash:
            return self._balance_hash
        if None not in (self.transferred_amount, self.locked_amount, self.locksroot):
            assert isinstance(self.transferred_amount, int)
            return encode_hex(
                self.hash_balance_data(
                    self.transferred_amount,
                    self.locked_amount,
                    self.locksroot,
                ),
            )
        raise ValueError("Can't compute balance hash")

    @balance_hash.setter
    def balance_hash(self, value) -> None:
        self._balance_hash = value

    @property
    def signer(self) -> str:
        signer = eth_recover(
            data=self.serialize_bin(),
            signature=decode_hex(self.signature),
        )
        return to_checksum_address(signer)

    @staticmethod
    def hash_balance_data(
        transferred_amount: int,
        locked_amount: int,
        locksroot: str,
    ) -> str:
        return Web3.soliditySha3(
            ['uint256', 'uint256', 'bytes32'],
            [transferred_amount, locked_amount, locksroot],
        )
