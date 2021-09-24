from functools import lru_cache
from typing import Union

import eth_utils
from eth_typing import AnyAddress, ChecksumAddress


@lru_cache(maxsize=5000)
def to_checksum_address(value: Union[AnyAddress, str, bytes]) -> ChecksumAddress:
    return eth_utils.to_checksum_address(value)
