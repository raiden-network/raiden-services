from enum import Enum, unique

from prometheus_client import CollectorRegistry, Counter

from raiden_libs.metrics import (
    REGISTRY,
    ERRORS_LOGGED,
    EVENTS_PROCESSING_TIME,
    EVENTS_EXCEPTIONS_RAISED,
    MESSAGES_PROCESSING_TIME,
    MESSAGES_EXCEPTIONS_RAISED,
    LabelErrorCategory,
    collect_event_metrics,
    collect_message_metrics
)



@unique
class LabelWho(Enum):
    US = "us"
    THEY = "they"


REWARD_CLAIMS = Counter(
    "economics_reward_claims_successful_total",
    "The number of overall successful reward claims",
    labelnames=["who"],
    registry=REGISTRY,
)

REWARD_CLAIMS_TOKEN = Counter(
    "economics_reward_claims_token_total",
    "The amount of token earned by reward claims",
    labelnames=["who"],
    registry=REGISTRY,
)

