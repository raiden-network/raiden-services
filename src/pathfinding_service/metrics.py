from prometheus_client import Gauge

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


class IouStatus(MetricsEnum):
    SUCCESSFUL = "successful"
    UNSUCCESSFUL = "unsuccessful"
    SKIPPED = "skipped"


IOU_CLAIMS = Gauge(
    "economics_iou_claims_total",
    "The number of overall IOU claims",
    labelnames=[IouStatus.label_name()],
    registry=REGISTRY,
)

IOU_CLAIMS_TOKEN = Gauge(
    "economics_iou_claims_token_total",
    "The amount of overall IOU token claimed",
    labelnames=[IouStatus.label_name()],
    registry=REGISTRY,
)
