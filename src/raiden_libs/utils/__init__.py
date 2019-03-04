from .signing import *  # noqa
from raiden_libs.types import ChannelIdentifier, T_ChannelIdentifier
from raiden.constants import UINT256_MAX


def is_channel_identifier(channel_identifier: ChannelIdentifier) -> bool:
    assert isinstance(channel_identifier, T_ChannelIdentifier)
    return 0 < channel_identifier <= UINT256_MAX
