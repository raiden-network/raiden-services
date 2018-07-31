from .merkle import *  # noqa
from .contracts import *  # noqa
from .signing import *  # noqa
from .private_key import *  # noqa
from raiden_libs.types import ChannelIdentifier, T_ChannelIdentifier


UINT64_MAX = (2**64) - 1
UINT192_MAX = (2**192) - 1
UINT256_MAX = (2**256) - 1


def is_channel_identifier(channel_identifier: ChannelIdentifier):
    assert isinstance(channel_identifier, T_ChannelIdentifier)
    return channel_identifier > 0 and channel_identifier <= UINT256_MAX
