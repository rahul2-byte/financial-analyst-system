from evals.live_metrics import aggregate_live_runs


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
