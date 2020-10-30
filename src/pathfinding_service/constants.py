import textwrap
from datetime import timedelta

from raiden.utils.typing import BlockTimeout

PFS_START_TIMEOUT = 300  # in seconds
API_PATH: str = "/api"

WEB3_PROVIDER_DEFAULT: str = "http://127.0.0.1:8545"

DIVERSITY_PEN_DEFAULT: int = 5
FEE_PEN_DEFAULT: int = 100
MAX_PATHS_PER_REQUEST: int = 25
DEFAULT_MAX_PATHS: int = 5  # number of paths return when no `max_path` argument is given

DEFAULT_REVEAL_TIMEOUT: BlockTimeout = BlockTimeout(50)

DEFAULT_SETTLE_TO_REVEAL_TIMEOUT_RATIO = 2

DEFAULT_INFO_MESSAGE = "This is your favorite PFS."

# When a new IOU session is started, this is the minimum number of blocks
# between the current block and `expiration_block`.
MIN_IOU_EXPIRY: int = 7 * 24 * 60 * 4

MAX_AGE_OF_IOU_REQUESTS: timedelta = timedelta(hours=1)
MAX_AGE_OF_FEEDBACK_REQUESTS: timedelta = timedelta(minutes=10)
CACHE_TIMEOUT_SUGGEST_PARTNER = timedelta(minutes=1)

PFS_DISCLAIMER: str = textwrap.dedent(
    """\
        +------------------------------------------------------------------------+
        | This is an Alpha version of experimental open source software released |
        | as a test version under an MIT license and may contain errors and/or   |
        | bugs. No guarantee or representation whatsoever is made regarding its  |
        | suitability (or its use) for any purpose or regarding its compliance   |
        | with any applicable laws and regulations. Use of the software is at    |
        | your own risk and discretion and by using the software you warrant and |
        | represent that you have read this disclaimer, understand its contents, |
        | assume all risk related thereto and hereby release, waive, discharge   |
        | and covenant not to hold liable Brainbot Labs Establishment or any of  |
        | its officers, employees or affiliates from and for any direct or       |
        | indirect damage resulting from the the software or the use thereof.    |
        | Such to the extent as permissible by applicable laws and regulations.  |
        |                                                                        |
        | Privacy Warning: Please be aware, that by using the Raiden Pathfinding |
        | service or Monitoring service among others, your Ethereum address,     |
        | account balance and your transactions will be stored on the Ethereum   |
        | chain, i.e. on servers of Ethereum node operators and ergo are to a    |
        | certain extent publicly available. The same might also be stored on    |
        | systems of parties running Raiden nodes connected to the same token    |
        | network. Data present in the Ethereum chain is very unlikely to be     |
        | able to be changed, removed or deleted from the public arena.          |
        |                                                                        |
        | This implementation follows the technical specification of             |
        | https://raiden-network-specification.readthedocs.io/en/latest/         |
        | Pathfinding service.                                                   |
        +------------------------------------------------------------------------+
    """
)
