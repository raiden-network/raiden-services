import textwrap
from datetime import timedelta

from raiden.utils.typing import BlockTimeout

DEFAULT_FILTER_INTERVAL: BlockTimeout = BlockTimeout(1_000)
MAX_FILTER_INTERVAL: BlockTimeout = BlockTimeout(100_000)
MIN_FILTER_INTERVAL: BlockTimeout = BlockTimeout(2)
DEFAULT_GAS_BUFFER_FACTOR: int = 10
DEFAULT_GAS_CHECK_BLOCKS: int = 100
KEEP_MRS_WITHOUT_CHANNEL: timedelta = timedelta(minutes=15)
# Make sure this stays <= Raiden's MONITORING_REWARD until there is a way to
# inform Raiden about the expected rewards.
DEFAULT_MIN_REWARD = 5 * 10 ** 18

# A LockedTransfer message is roughly 1kb. Having 1000/min = 17/sec will be
# hard to achieve outside of benchmarks for now. To have some safety margin for
# bursts of messages, this is only enforced as an average over 5 minutes.
MATRIX_RATE_LIMIT_ALLOWED_BYTES = 5_000_000
MATRIX_RATE_LIMIT_RESET_INTERVAL = timedelta(minutes=5)

# Number of blocks after the close, during which MRs are still being accepted
CHANNEL_CLOSE_MARGIN: int = 10

API_PATH: str = "/api"
DEFAULT_INFO_MESSAGE = "This is your favorite MS."

MS_DISCLAIMER: str = textwrap.dedent(
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
        | able to be changed, removed or deleted from the public arena. Also be  |
        | aware, that data on individual MonitorRequests will be made available  |
        | via the Matrix protocol to all users and Matrix server operators.      |
        |                                                                        |
        | This implementation follows the technical specification of             |
        | https://raiden-network-specification.readthedocs.io/en/latest/         |
        | Monitoring service.                                                    |
        +------------------------------------------------------------------------+
    """
)
