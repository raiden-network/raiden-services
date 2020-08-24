from contextlib import contextmanager
from enum import Enum, unique
from typing import Generator, Tuple

from prometheus_client import CollectorRegistry, Counter, Histogram
from prometheus_client import CollectorRegistry, Counter, Histogram
from prometheus_client.context_managers import ExceptionCounter, Timer

from raiden_libs.events import Event
from raiden.messages.abstract import Message


REGISTRY = CollectorRegistry(auto_describe=True)


MetricsGenerator = Generator[Tuple[Timer, ExceptionCounter], None, None]


@unique
class LabelErrorCategory(Enum):
    STATE = "state"
    BLOCKCHAIN = "blockchain"
    PROTOCOL = "protocol"


ERRORS_LOGGED = Counter(
    "events_log_errors_total",
    "The number of errors that were written to the log.",
    labelnames=["error_category"],
    registry=REGISTRY,
)


EVENTS_EXCEPTIONS_RAISED = Counter(
    "events_exceptions_total",
    "The number of exceptions that were raised in event handlers",
    labelnames=["event_type"],
    registry=REGISTRY,
)


EVENTS_PROCESSING_TIME = Histogram(
    "events_processing_duration_seconds",
    "The overall time it takes for an event to get processed",
    labelnames=["event_type"],
    registry=REGISTRY,
)


MESSAGES_EXCEPTIONS_RAISED = Counter(
    "messages_exceptions_total",
    "The number of exceptions that were raised in event handlers",
    labelnames=["message_type"],
    registry=REGISTRY,
)


MESSAGES_PROCESSING_TIME = Histogram(
    "messages_processing_duration_seconds",
    "The overall time it takes for an message to get processed",
    labelnames=["message_type"],
    registry=REGISTRY,
)


def report_error(error_category: LabelErrorCategory) -> None:
    """ Convenience method to increase the error logged counter for a certain error category """
    ERRORS_LOGGED.labels(error_category=error_category).inc()


@contextmanager
def collect_event_metrics(event: Event) -> MetricsGenerator:
    event_type = event.__class__.__name__
    with EVENTS_PROCESSING_TIME.labels(
        event_type=event_type
    ).time() as timer, EVENTS_EXCEPTIONS_RAISED.labels(
        event_type=event_type
    ).count_exceptions() as exception_counter:
        yield (timer, exception_counter)


@contextmanager
def collect_message_metrics(message: Message) -> MetricsGenerator:
    message_type = message.__class__.__name__
    with MESSAGES_PROCESSING_TIME.labels(message_type=message_type
    ).time() as timer, MESSAGES_EXCEPTIONS_RAISED.labels(
        message_type=message_type
    ).count_exceptions() as exception_counter:
        yield (timer, exception_counter)

