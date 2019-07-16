from datetime import timedelta

DEFAULT_REQUIRED_CONFIRMATIONS: int = 10
MAX_FILTER_INTERVAL: int = 100_000
DEFAULT_GAS_BUFFER_FACTOR: int = 10
DEFAULT_GAS_CHECK_BLOCKS: int = 100
DEFAULT_PAYMENT_RISK_FAKTOR: int = 2
KEEP_MRS_WITHOUT_CHANNEL: timedelta = timedelta(minutes=15)

# A LockedTransfer message is roughly 1kb. Having 1000/min = 17/sec will be
# hard to achieve outside of benchmarks for now. To have some safety margin for
# bursts of messages, this is only enforced as an average over 5 minutes.
MATRIX_RATE_LIMIT_ALLOWED_BYTES = 5_000_000
MATRIX_RATE_LIMIT_RESET_INTERVAL = timedelta(minutes=5)
