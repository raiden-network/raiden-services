from typing import List

import pytest
from prometheus_client.metrics import Metric

from raiden_libs import metrics


@pytest.fixture
def prometheus_client_collectors() -> List[Metric]:
    return [
        metrics.ERRORS_LOGGED,
        metrics.EVENTS_PROCESSING_TIME,
        metrics.EVENTS_EXCEPTIONS_RAISED,
        metrics.MESSAGES_PROCESSING_TIME,
        metrics.MESSAGES_EXCEPTIONS_RAISED
    ]


@pytest.fixture
def prometheus_client_teardown(prometheus_client_collectors) -> None:
    for collector in prometheus_client_collectors:
        # HACK access private attr. in order to easily delete the samples
        # Since the library doesn't have a reliable way of accessing the tuple
        # of label values this is as hacky as any other solution
        for vals in list(collector._metrics.keys()):  # pylint: disable=protected-access
            collector.remove(*vals)

