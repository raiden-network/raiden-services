from typing import List

from prometheus_client import Metric
import pytest

from monitoring_service import metrics


@pytest.fixture
def prometheus_client_collectors(prometheus_client_collectors) -> List[Metric]:
    return prometheus_client_collectors + [metrics.REWARD_CLAIMS, metrics.REWARD_CLAIMS_TOKEN]
