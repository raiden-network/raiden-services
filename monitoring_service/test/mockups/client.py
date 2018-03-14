from monitoring_service.utils import privkey_to_addr
from eth_utils import is_checksum_address, remove_0x_prefix, is_same_address, encode_hex
from monitoring_service.messages import BalanceProof
from coincurve import PrivateKey
from functools import wraps
from sha3 import keccak_256

NULL_ADDRESS = '0x0000000000000000000000000000000000000000'


def sha3(data):
    return keccak_256(data).digest()


def assert_channel_existence(func):
    @wraps(func)
    def func_wrapper(self, partner_address, *args, **kwargs):
        assert is_checksum_address(partner_address)
        assert partner_address in self.channels
        return func(self, partner_address, *args, **kwargs)
    return func_wrapper


class MockRaidenNode:
    def __init__(self, privkey, channel_contract):
        self.privkey = privkey
        self.address = privkey_to_addr(privkey)
        self.contract = channel_contract
        self.channels = dict()
        self.netting_channel_abi = None
        self.web3 = self.contract.web3

    def open_channel(self, partner_address):
        assert is_checksum_address(partner_address)
        # fist check if channel exists
        channel_address = self.get_existing_channel(partner_address)
        if is_same_address(channel_address, NULL_ADDRESS):
            # if it doesn't exist, register new channel
            txid = self.contract.transact({'from': self.address}).newChannel(partner_address, 15)
            assert txid is not None
            channel_address = self.contract.call(
                {'from': self.address}
            ).getChannelWith(partner_address)
        assert is_checksum_address(channel_address)
        self.channels[partner_address] = self.web3.eth.contract(
            abi=self.netting_channel_abi,
            address=channel_address
        )
        return channel_address

    @assert_channel_existence
    def deposit_to_channel(self, partner_address, amount):
        channel_contract = self.channels[partner_address]
        self.token_contract.transact(
            {'from': self.address}
        ).approve(channel_contract.address, amount)
        return channel_contract.transact({'from': self.address}).deposit(amount)

    def get_existing_channel(self, partner_address):
        """Will return 0x00..00 if channel does not exist"""
        return self.contract.call({'from': self.address}).getChannelWith(partner_address)

    @assert_channel_existence
    def close_channel(self, partner_address, balance_proof=None):
        channel_contract = self.channels[partner_address]
        if balance_proof is None:
            balance_proof = BalanceProof(
                channel_contract.address,
                self.address,
                partner_address
            )

        channel_contract.transact({'from': self.address}).close(
            balance_proof.nonce,
            balance_proof.transferred_amount,
            balance_proof.locksroot,
            balance_proof.extra_hash,
            balance_proof.signature
        )

    @assert_channel_existence
    def settle_channel(self, partner_address):
        channel_contract = self.channels[partner_address]
        channel_contract.transact({'from': self.address}).settle()

    @assert_channel_existence
    def get_balance_proof(self, partner_address, value):
        channel_contract = self.channels[partner_address]
        bp = BalanceProof(
            channel_contract.address,
            self.address,
            partner_address,
            transferred_amount=value
        )
        bp.signature = encode_hex(self.sign_data(bp.serialize_bin(), self.privkey))
        return bp

    @assert_channel_existence
    def update_transfer(self, partner_address, balance_proof):
        channel_contract = self.channels[partner_address]
        channel_contract.transact({'from': self.address}).updateTransfer(
            balance_proof.nonce,
            balance_proof.transferred_amount,
            balance_proof.locksroot,
            balance_proof.extra_hash,
            balance_proof.signature
        )

    @staticmethod
    def sign_data(data, privkey):
        pk = PrivateKey.from_hex(remove_0x_prefix(privkey))
        sig = pk.sign_recoverable(data, hasher=sha3)
        return sig[:-1] + chr(sig[-1] + 27).encode()
