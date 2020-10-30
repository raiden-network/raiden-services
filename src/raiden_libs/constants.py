# Since the UDC deposits are not double spend safe, you want a higher deposit
# than you're able to claim to reduce the possibility of double spends.
UDC_SECURITY_MARGIN_FACTOR_MS: float = 1.1
UDC_SECURITY_MARGIN_FACTOR_PFS: float = 2

MATRIX_START_TIMEOUT = 240  # in seconds

CONFIRMATION_OF_UNDERSTANDING = (
    "Have you read, understood and hereby accept the above disclaimer and privacy warning?"
)

DEFAULT_POLL_INTERVALL = 2


DEFAULT_API_HOST: str = "localhost"
DEFAULT_API_PORT_PFS: int = 6000
DEFAULT_API_PORT_MS: int = 6001
