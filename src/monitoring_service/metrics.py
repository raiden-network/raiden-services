from prometheus_client import Counter

from raiden.utils.typing import TokenAmount
from raiden_libs.metrics import (  # noqa: F401, pylint: disable=unused-import
    ERRORS_LOGGED,
    EVENTS_EXCEPTIONS_RAISED,
    EVENTS_PROCESSING_TIME,
    MESSAGES_EXCEPTIONS_RAISED,
    MESSAGES_PROCESSING_TIME,
    REGISTRY,
    ErrorCategory,
    MetricsEnum,
    collect_event_metrics,
    collect_message_metrics,
    get_metrics_for_label,
)


class Who(MetricsEnum):
    US = "us"
    THEY = "they"


REWARD_CLAIMS = Counter(
    "economics_reward_claims_successful_total",
    "The number of overall successful reward claims",
    labelnames=[Who.label_name()],
    registry=REGISTRY,
)

REWARD_CLAIMS_TOKEN = Counter(
    "economics_reward_claims_token_total",
    "The amount of token earned by reward claims",
    labelnames=[Who.label_name()],
    registry=REGISTRY,
)


def report_increased_reward_claims(amount: TokenAmount, who: Who) -> None:
    get_metrics_for_label(REWARD_CLAIMS, who).inc()
    get_metrics_for_label(REWARD_CLAIMS_TOKEN, who).inc(float(amount))
