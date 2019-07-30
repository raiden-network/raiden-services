from datetime import timedelta

API_PATH: str = "/api/v1"
DEFAULT_API_HOST: str = "localhost"
DEFAULT_API_PORT: int = 6000

WEB3_PROVIDER_DEFAULT: str = "http://127.0.0.1:8545"

DIVERSITY_PEN_DEFAULT: int = 5
FEE_PEN_DEFAULT: int = 100
MAX_PATHS_PER_REQUEST: int = 25
DEFAULT_MAX_PATHS: int = 5  # number of paths return when no `max_path` argument is given

DEFAULT_REVEAL_TIMEOUT: int = 50

DEFAULT_SETTLE_TO_REVEAL_TIMEOUT_RATIO = 2

DEFAULT_POLL_INTERVALL = 2
DEFAULT_INFO_MESSAGE = "This is your favorite pfs for token network registry "

# When a new IOU session is started, this is the minimum number of blocks
# between the current block and `expiration_block`.
MIN_IOU_EXPIRY: int = 7 * 24 * 60 * 4

MAX_AGE_OF_IOU_REQUESTS: timedelta = timedelta(hours=1)
MAX_AGE_OF_FEEDBACK_REQUESTS: timedelta = timedelta(minutes=10)

# Since the UDC deposits are not double spend safe, you want a higher deposit
# than you're able to claim to reduce the possibility of double spends.
UDC_SECURITY_MARGIN_FACTOR: float = 2
