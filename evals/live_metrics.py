"""Aggregation of operational live-provider run records."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from math import ceil
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


def aggregate_run_events(
    events: list[dict[str, Any]], pricing: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Aggregate a local typed-event ledger without inferring missing data."""
    by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        run_id = event.get("run_id")
        if run_id:
            by_run[str(run_id)].append(event)

    def payload(event: dict[str, Any]) -> dict[str, Any]:
        value = event.get("payload", {})
        return value if isinstance(value, dict) else {}

    def percentile(values: list[float], quantile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, ceil(len(ordered) * quantile) - 1))
        return round(ordered[index], 2)

    def samples(values: list[float], missing: int) -> dict[str, Any]:
        return {
            "sample_count": len(values),
            "missing_count": missing,
            "p50": percentile(values, 0.50),
            "p95": percentile(values, 0.95),
        }

    attempted = len(by_run)
    statuses = {
        "completed": 0,
        "completed_with_limited_evidence": 0,
        "partial": 0,
        "failed": 0,
        "other": 0,
    }
    end_to_end: list[float] = []
    provider_latency: list[float] = []
    missing_end_to_end = 0
    missing_provider_latency = 0
    retry_count = 0
    timeout_count = 0
    usage_values: dict[str, list[int]] = {
        "prompt_tokens": [],
        "completion_tokens": [],
        "total_tokens": [],
    }
    usage_missing = {name: 0 for name in usage_values}
    costs: list[Decimal] = []
    failure_examples: list[dict[str, Any]] = []

    for run_id, run_events in by_run.items():
        ordered = sorted(run_events, key=lambda item: str(item.get("occurred_at", "")))
        started = next(
            (event for event in ordered if event.get("event_type") == "run.started"),
            None,
        )
        terminals = [
            event
            for event in ordered
            if event.get("event_type")
            in {"run.completed", "run.failed", "run.cancelled"}
        ]
        terminal = terminals[-1] if terminals else None
        terminal_payload = payload(terminal) if terminal else {}
        provider_terminals = [
            event
            for event in ordered
            if event.get("event_type") in {"provider.completed", "provider.failed"}
        ]
        provider_terminal = provider_terminals[-1] if provider_terminals else None
        provider_payload = payload(provider_terminal) if provider_terminal else {}
        partial_provider = any(
            event.get("event_type") == "provider.failed"
            and payload(event).get("partial_output") is True
            for event in ordered
        )
        terminal_status = str(terminal_payload.get("terminal_status", ""))
        if (
            terminal
            and terminal.get("event_type") == "run.completed"
            and terminal_status in {"success", "completed"}
        ):
            status = "completed"
        elif terminal_status == "completed_with_limited_evidence":
            status = "completed_with_limited_evidence"
        elif partial_provider or terminal_status == "partial":
            status = "partial"
        elif terminal or provider_terminals:
            status = "failed"
        else:
            status = "other"
        statuses[status] += 1

        if started and terminal:
            try:
                start_time = _parse_time(started["occurred_at"])
                end_time = _parse_time(terminal["occurred_at"])
                end_to_end.append((end_time - start_time).total_seconds() * 1000)
            except (KeyError, TypeError, ValueError):
                missing_end_to_end += 1
        else:
            missing_end_to_end += 1

        if (
            provider_terminal is not None
            and provider_payload.get("duration_ms") is not None
        ):
            provider_latency.append(float(provider_payload["duration_ms"]))
        else:
            missing_provider_latency += 1
        retry_count += sum(
            event.get("event_type") == "provider.retrying" for event in ordered
        )
        timeout_count += int(
            any(
                event.get("event_type") == "provider.failed"
                and (
                    payload(event).get("timeout") is True
                    or payload(event).get("phase") == "timeout"
                )
                for event in ordered
            )
        )

        usage = provider_payload.get("usage")
        usage = usage if isinstance(usage, dict) else None
        usage_data: dict[str, Any] = usage if usage is not None else {}
        model_id = provider_payload.get("model_id")
        for name, values in usage_values.items():
            value = usage_data.get(name)
            if (
                isinstance(value, int)
                and value >= 0
                and usage_data.get("verified") is True
            ):
                values.append(value)
            else:
                usage_missing[name] += 1
        if _verified_usage(usage_data) and model_id:
            cost = _cost_for_usage(usage_data, model_id, pricing)
            if cost is not None:
                costs.append(cost)

        if status in {"failed", "partial"} and len(failure_examples) < 50:
            failure = next(
                (
                    event
                    for event in reversed(ordered)
                    if event.get("event_type")
                    in {"run.failed", "run.cancelled", "provider.failed"}
                ),
                None,
            )
            failure_examples.append(
                {"run_id": run_id, "event": failure} if failure else {"run_id": run_id}
            )

    denominator = attempted
    return {
        "runs": {
            name: {"count": count, "denominator": denominator}
            for name, count in statuses.items()
        },
        "end_to_end_latency_ms": samples(end_to_end, missing_end_to_end),
        "provider_latency_ms": samples(provider_latency, missing_provider_latency),
        "retries": {"count": retry_count, "denominator": denominator},
        "timeouts": {"count": timeout_count, "denominator": denominator},
        "token_usage": {
            name: {
                "sample_count": len(values),
                "missing_count": usage_missing[name],
                "sum_known": sum(values) if values else None,
            }
            for name, values in usage_values.items()
        },
        "cost": {
            "status": _cost_status(costs, pricing),
            "pricing_version": pricing.get("version") if pricing else None,
            "sample_count": len(costs),
            "total_usd": float(sum(costs, Decimal(0))) if costs else None,
        },
        "failure_examples": failure_examples,
    }


def aggregate_stage_timings(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate explicit stage.started/stage.completed event pairs."""
    by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("run_id"):
            by_run[str(event["run_id"])].append(event)
    values: dict[str, list[float]] = defaultdict(list)
    missing: dict[str, int] = defaultdict(int)
    for run_events in by_run.values():
        starts = {(str(event.get("stage")), str(event.get("label"))): event for event in run_events if event.get("event_type") == "stage.started"}
        for event in run_events:
            if event.get("event_type") != "stage.completed":
                continue
            key = (str(event.get("stage")), str(event.get("label")))
            start = starts.get(key)
            if start is None:
                missing[key[1]] += 1
                continue
            try:
                elapsed = (_parse_time(event["occurred_at"]) - _parse_time(start["occurred_at"])).total_seconds() * 1000
            except (KeyError, TypeError, ValueError):
                missing[key[1]] += 1
            else:
                values[key[1]].append(elapsed)

    def percentile(samples: list[float], q: float) -> float | None:
        if not samples:
            return None
        ordered = sorted(samples)
        return round(ordered[min(len(ordered) - 1, max(0, int(len(ordered) * q) - 1))], 2)

    return {
        label: {
            "sample_count": len(samples),
            "missing_count": missing.get(label, 0),
            "p50": percentile(samples, 0.5),
            "p95": percentile(samples, 0.95),
            "p99": percentile(samples, 0.99) if len(samples) >= 200 else None,
        }
        for label, samples in values.items()
    }


def _parse_time(value: Any):
    from datetime import datetime

    return datetime.fromisoformat(str(value))


def _verified_usage(usage: Any) -> bool:
    return (
        isinstance(usage, dict)
        and usage.get("verified") is True
        and all(
            isinstance(usage.get(name), int) and usage[name] >= 0
            for name in ("prompt_tokens", "completion_tokens")
        )
    )


def _cost_for_usage(
    usage: dict[str, Any], model_id: str, pricing: dict[str, Any] | None
) -> Decimal | None:
    if not pricing or not pricing.get("version"):
        return None
    model = pricing.get("models", {}).get(model_id, {})
    try:
        prompt_rate = Decimal(str(model["prompt_per_1k_usd"]))
        completion_rate = Decimal(str(model["completion_per_1k_usd"]))
        return (
            Decimal(usage["prompt_tokens"]) * prompt_rate
            + Decimal(usage["completion_tokens"]) * completion_rate
        ) / Decimal(1000)
    except (KeyError, TypeError, InvalidOperation):
        return None


def _cost_status(costs: list[Decimal], pricing: dict[str, Any] | None) -> str:
    if costs:
        return "verified"
    if not pricing or not pricing.get("version"):
        return "missing_pricing"
    return "missing_verified_usage_or_model_rate"
