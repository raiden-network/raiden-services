from .signing import *  # noqa
from raiden_libs.types import ChannelIdentifier, T_ChannelIdentifier


UINT64_MAX = (2**64) - 1
UINT192_MAX = (2**192) - 1
UINT256_MAX = (2**256) - 1


def is_channel_identifier(channel_identifier: ChannelIdentifier) -> bool:
    assert isinstance(channel_identifier, T_ChannelIdentifier)
    return 0 < channel_identifier <= UINT256_MAX
