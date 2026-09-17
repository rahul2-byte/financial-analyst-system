"""Small process-local provider outcome counters."""

from __future__ import annotations


class ProviderMetrics:
    def __init__(self) -> None:
        self._requests = 0
        self._failures = 0
        self._timeouts = 0
        self._partial_outputs = 0
        self._latencies: list[float] = []

    def record(
        self, *, status: str, latency_ms: float, timeout: bool, partial: bool
    ) -> None:
        self._requests += 1
        self._failures += status != "completed"
        self._timeouts += timeout
        self._partial_outputs += partial
        self._latencies.append(latency_ms)

    def snapshot(self) -> dict[str, float | int]:
        requests = self._requests or 1
        return {
            "requests": self._requests,
            "failures": self._failures,
            "timeouts": self._timeouts,
            "partial_outputs": self._partial_outputs,
            "failure_rate": self._failures / requests,
            "timeout_rate": self._timeouts / requests,
            "partial_output_rate": self._partial_outputs / requests,
            "mean_latency_ms": sum(self._latencies) / requests,
        }
