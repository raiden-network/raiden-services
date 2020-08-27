from typing import Dict, List, Optional

from prometheus_client import CollectorRegistry, Metric


class MetricsRelativeState:
    def __init__(self, registry: CollectorRegistry) -> None:
        self._registry = registry
        self._state_save_collected: List[Metric] = []

    @property
    def has_saved_state(self) -> bool:
        return bool(self._state_save_collected)

    def save_state(self) -> None:
        # collect() will collect all metrics with their samples, but the
        # objects will not get modified afterwards!
        self._state_save_collected = list(self._registry.collect())

    def get_delta(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        # if they are not known in either of the registries, just assign them a 0. value for now
        before = self.get_saved_sample_value(name, labels=labels) or 0.0
        after = self._registry.get_sample_value(name, labels=labels) or 0.0

        if not isinstance(after, type(before)):
            raise TypeError(
                "Sample value changed type after saving the state. This is not expected!"
            )

        return after - before

    def get_saved_sample_value(
        self, name: str, labels: Optional[Dict[str, str]] = None
    ) -> Optional[float]:
        if not self.has_saved_state:
            raise RuntimeError(
                "No state was saved. Call .save_state() before querying delta values!"
            )
        if labels is None:
            labels = {}
        for metric in self._state_save_collected:
            for sample in metric.samples:
                if sample.name == name and sample.labels == labels:
                    return sample.value
        return None


def save_metrics_state(registry: CollectorRegistry) -> MetricsRelativeState:
    state = MetricsRelativeState(registry)
    state.save_state()
    return state
