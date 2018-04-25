import jsonschema

from web3 import Web3
from eth_utils import is_address, decode_hex

from raiden_libs.messages.message import Message
from raiden_libs.properties import address_property
from raiden_libs.messages.json_schema import BALANCE_PROOF_SCHEMA
from raiden_libs.utils import eth_verify
from raiden_libs.types import Address, ChannelIdentifier


class BalanceProof(Message):
    """ A Balance Proof

    This optionally includse the data for calculating the balance_hash.
    """
    def __init__(
        self,
        channel_identifier: ChannelIdentifier,
        token_network_address: Address,

        balance_hash: str = '',
        nonce: int = 0,
        additional_hash: str = '',
        chain_id: int = 1,
        signature: str = '',

        transferred_amount: int = None,
        locked_amount: int = None,
        locksroot: str = None,
    ) -> None:
        super().__init__()
        assert channel_identifier > 0
        assert is_address(token_network_address)

        self._type = 'BalanceProof'

        self.channel_identifier = channel_identifier
        self.token_network_address = token_network_address

        self.balance_hash = balance_hash
        self.additional_hash = additional_hash
        self.nonce = nonce
        self.chain_id = chain_id
        self.signature = signature

        if transferred_amount and locked_amount and locksroot:
            assert self.hash_balance_data(
                transferred_amount,
                locked_amount,
                locksroot
            ) == self.balance_hash

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

        if self.transferred_amount and self.locked_amount and self.locksroot:
            result['transferred_amount'] = self.transferred_amount
            result['locked_amount'] = self.locked_amount
            result['locksroot'] = self.locksroot

        return result

    def serialize_bin(self):
        return Web3.soliditySha3([
            'bytes32',
            'uint256',
            'bytes32',
            'uint256',
            'address',
            'uint256'
        ], [
            self.balance_hash.encode(),
            self.nonce,
            self.additional_hash.encode(),
            self.channel_identifier,
            self.token_network_address,
            self.chain_id
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
            signature=data['signature']
        )
        return result

    token_network_address = address_property('_contract')  # type: ignore
    json_schema = BALANCE_PROOF_SCHEMA

    @property
    def signer(self) -> str:
        return eth_verify(
            decode_hex(self.signature),
            self.serialize_bin()
        )

    def hash_balance_data(
        self,
        transferred_amount: int,
        locked_amount: int,
        locksroot: str
    ) -> str:
        return Web3.soliditySha3(
            ['uint256', 'uint256', 'bytes32'],
            [transferred_amount, locked_amount, locksroot]
        )

    # def sign_balance_proof(
    #         privatekey,
    #         token_network_address,
    #         chain_identifier,
    #         channel_identifier,
    #         balance_hash,
    #         nonce,
    #         additional_hash,
    #         v=27):
    #     message_hash = hash_balance_proof(
    #         token_network_address,
    #         chain_identifier,
    #         channel_identifier,
    #         balance_hash,
    #         nonce,
    #         additional_hash
    #     )
    #
    #     return sign(privatekey, message_hash, v)
