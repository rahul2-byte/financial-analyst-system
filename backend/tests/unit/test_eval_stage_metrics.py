from evals.live_metrics import aggregate_stage_timings


def test_stage_timings_withhold_p99_for_small_samples():
    events = [
        {"run_id": "r1", "event_type": "stage.started", "stage": "validation", "label": "validation", "occurred_at": "2026-01-01T00:00:00+00:00"},
        {"run_id": "r1", "event_type": "stage.completed", "stage": "validation", "label": "validation", "occurred_at": "2026-01-01T00:00:00.010000+00:00"},
    ]
    result = aggregate_stage_timings(events)
    assert result["validation"]["p50"] == 10.0
    assert result["validation"]["p99"] is None
