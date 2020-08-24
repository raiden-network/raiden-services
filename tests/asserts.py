from typing import Optional, Dict, Any
from raiden_libs import metrics


def assert_metrics_has(namespace: str, value: Any, labels: Optional[Dict[str, str]] = None):
    assert metrics.REGISTRY.get_sample_value(namespace, labels=labels) == value

