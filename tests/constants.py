from eth_utils import decode_hex

from raiden.utils.typing import ChainID, ChannelID, MonitoringServiceAddress, TokenNetworkAddress
from raiden_libs.utils import private_key_to_address

KEYSTORE_FILE_NAME = "keystore.txt"
KEYSTORE_PASSWORD = "password"
TEST_MSC_ADDRESS = MonitoringServiceAddress(b"9" * 20)
TEST_CHAIN_ID = ChainID(131277322940537)

DEFAULT_TOKEN_NETWORK_ADDRESS = TokenNetworkAddress(
    decode_hex("0x6e46B62a245D9EE7758B8DdCCDD1B85fF56B9Bc9")
)
DEFAULT_TOKEN_NETWORK_SETTLE_TIMEOUT = 1500  # time in seconds
PRIVATE_KEY_1 = bytes([1] * 32)
PRIVATE_KEY_1_ADDRESS = private_key_to_address(PRIVATE_KEY_1)
PRIVATE_KEY_2 = bytes([2] * 32)
PRIVATE_KEY_2_ADDRESS = private_key_to_address(PRIVATE_KEY_2)
PRIVATE_KEY_3 = bytes([3] * 32)
PRIVATE_KEY_3_ADDRESS = private_key_to_address(PRIVATE_KEY_3)
DEFAULT_CHANNEL_ID = ChannelID(0)
