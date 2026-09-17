"""Aggregation of operational live-provider run records."""

from __future__ import annotations

from statistics import median
from typing import Any


def aggregate_live_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Return rates with explicit attempted-run denominators."""
    attempted = len(runs)
    failed = sum(bool(run.get("failed", False)) for run in runs)
    timed_out = sum(bool(run.get("timed_out", False)) for run in runs)
    partial = sum(bool(run.get("partial_output", False)) for run in runs)
    latencies = [
        float(run["latency_ms"]) for run in runs if run.get("latency_ms") is not None
    ]

    def rate(count: int) -> float:
        return round(count / attempted, 6) if attempted else 0.0

    return {
        "attempted_runs": attempted,
        "failure_rate": rate(failed),
        "timeout_rate": rate(timed_out),
        "partial_output_rate": rate(partial),
        "latency_ms": {
            "sample_count": len(latencies),
            "median": round(median(latencies), 2) if latencies else None,
            "min": min(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
    }
