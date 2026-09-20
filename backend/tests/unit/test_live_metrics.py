from typing import Any

from evals.live_metrics import aggregate_live_runs, aggregate_run_events


def test_live_metrics_use_attempted_runs_as_denominator() -> None:
    result = aggregate_live_runs(
        [
            {
                "failed": True,
                "timed_out": True,
                "partial_output": False,
                "latency_ms": 100,
            },
            {
                "failed": False,
                "timed_out": False,
                "partial_output": True,
                "latency_ms": 200,
            },
        ]
    )

    assert result["attempted_runs"] == 2
    assert result["failure_rate"] == 0.5
    assert result["timeout_rate"] == 0.5
    assert result["partial_output_rate"] == 0.5
    assert result["latency_ms"]["median"] == 150


def test_live_metrics_are_zero_safe() -> None:
    result = aggregate_live_runs([])
    assert result["attempted_runs"] == 0
    assert result["failure_rate"] == 0.0
    assert result["latency_ms"]["sample_count"] == 0


def test_run_event_metrics_are_zero_safe() -> None:
    result = aggregate_run_events([])

    assert result["runs"]["completed"] == {"count": 0, "denominator": 0}
    assert result["end_to_end_latency_ms"]["p50"] is None
    assert result["token_usage"]["total_tokens"]["missing_count"] == 0
    assert result["cost"]["status"] == "missing_pricing"


def test_run_event_metrics_preserve_partial_stream_and_missing_usage() -> None:
    events: list[dict[str, Any]] = [
        {
            "run_id": "run-partial",
            "event_type": "run.started",
            "occurred_at": "2026-09-19T10:00:00+00:00",
            "payload": {},
        },
        {
            "run_id": "run-partial",
            "event_type": "provider.failed",
            "occurred_at": "2026-09-19T10:00:00.250000+00:00",
            "payload": {
                "phase": "transport",
                "partial_output": True,
                "timeout": False,
                "duration_ms": 250,
                "message": "connection reset",
            },
        },
    ]

    result = aggregate_run_events(events)

    assert result["runs"]["partial"] == {"count": 1, "denominator": 1}
    assert result["runs"]["failed"]["count"] == 0
    assert result["token_usage"]["prompt_tokens"] == {
        "sample_count": 0,
        "missing_count": 1,
        "sum_known": None,
    }
    assert result["failure_examples"][0]["run_id"] == "run-partial"


def test_run_event_metrics_cost_requires_verified_usage_and_pricing() -> None:
    events: list[dict[str, Any]] = [
        {
            "run_id": "run-complete",
            "event_type": "run.started",
            "occurred_at": "2026-09-19T10:00:00+00:00",
            "payload": {},
        },
        {
            "run_id": "run-complete",
            "event_type": "provider.completed",
            "occurred_at": "2026-09-19T10:00:00.100000+00:00",
            "payload": {
                "model_id": "fixture-model",
                "duration_ms": 100,
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            },
        },
        {
            "run_id": "run-complete",
            "event_type": "run.completed",
            "occurred_at": "2026-09-19T10:00:00.200000+00:00",
            "payload": {"terminal_status": "success"},
        },
    ]

    without_verified_usage = aggregate_run_events(
        events, {"version": "v1", "models": {}}
    )
    assert without_verified_usage["cost"]["total_usd"] is None
    assert (
        without_verified_usage["cost"]["status"]
        == "missing_verified_usage_or_model_rate"
    )

    usage = events[1]["payload"]["usage"]
    assert isinstance(usage, dict)
    usage["verified"] = True
    priced = aggregate_run_events(
        events,
        {
            "version": "v1",
            "models": {
                "fixture-model": {
                    "prompt_per_1k_usd": "1.0",
                    "completion_per_1k_usd": "2.0",
                }
            },
        },
    )
    assert priced["cost"]["status"] == "verified"
    assert priced["cost"]["total_usd"] == 0.008
    assert priced["token_usage"]["prompt_tokens"]["sum_known"] == 4
