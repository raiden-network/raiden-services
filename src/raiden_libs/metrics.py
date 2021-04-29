from contextlib import contextmanager
from enum import Enum, unique
from typing import Dict, Generator, Tuple

from prometheus_client import CollectorRegistry, Counter, Histogram, Metric
from prometheus_client.context_managers import ExceptionCounter, Timer

from raiden.messages.abstract import Message
from raiden_libs.events import Event
from raiden_libs.utils import camel_to_snake

REGISTRY = CollectorRegistry(auto_describe=True)


MetricsGenerator = Generator[Tuple[Timer, ExceptionCounter], None, None]


@unique
class MetricsEnum(Enum):
    def __str__(self) -> str:
        return str(self.value)

    @classmethod
    def label_name(cls) -> str:
        return camel_to_snake(cls.__name__)

    def to_label_dict(self) -> Dict[str, str]:
        return {self.label_name(): str(self)}


class ErrorCategory(MetricsEnum):
    STATE = "state"
    BLOCKCHAIN = "blockchain"
    PROTOCOL = "protocol"


ERRORS_LOGGED = Counter(
    "events_log_errors_total",
    "The number of errors that were written to the log.",
    labelnames=[ErrorCategory.label_name()],
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
    with MESSAGES_PROCESSING_TIME.labels(
        message_type=message_type
    ).time() as timer, MESSAGES_EXCEPTIONS_RAISED.labels(
        message_type=message_type
    ).count_exceptions() as exception_counter:
        yield (timer, exception_counter)


def get_metrics_for_label(metric: Metric, enum: MetricsEnum) -> Metric:
    return metric.labels(**enum.to_label_dict())


def report_error(error_category: ErrorCategory) -> None:
    """Convenience method to increase the error logged counter for a certain error category"""
    get_metrics_for_label(ERRORS_LOGGED, error_category).inc()
