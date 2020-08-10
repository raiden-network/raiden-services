from contextlib import contextmanager
from typing import Generator

from prometheus_client import Counter, Histogram

from raiden_libs.events import Event

REWARD_CLAIMS = Counter(
    "economics_reward_claims_successful_total",
    "The number of overall successful reward claims",
    labelnames=["who"],
)


REWARD_CLAIMS_TOKEN = Counter(
    "economics_reward_claims_token_total",
    "The amount of token earned by reward claims",
    labelnames=["who"],
)


ERRORS_LOGGED = Counter(
    "events_log_errors_total",
    "The number of errors that were written to the log.",
    labelnames=["error_category"],
)


EVENTS_EXCEPTIONS_RAISED = Counter(
    "events_exceptions_total",
    "The number of exceptions that were raised in event handlers",
    labelnames=["event_type"],
)

EVENTS_PROCESSING_TIME = Histogram(
    "events_processing_duration_seconds",
    "The overall time it takes for an event to get processed",
    labelnames=["event_type"],
)


@contextmanager
def collect_event_metrics(event: Event) -> Generator:
    event_type = event.__class__.__name__
    with EVENTS_PROCESSING_TIME.labels(
        event_type=event_type
    ).time() as timer, EVENTS_EXCEPTIONS_RAISED.labels(
        event_type=event_type
    ).count_exceptions() as exception_counter:
        yield (timer, exception_counter)
