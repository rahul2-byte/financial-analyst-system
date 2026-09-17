from app.observability.provider_metrics import ProviderMetrics


def test_provider_metrics_reports_failure_timeout_latency_and_partial_rates() -> None:
    metrics = ProviderMetrics()
    metrics.record(status="completed", latency_ms=10.0, timeout=False, partial=False)
    metrics.record(status="failed", latency_ms=20.0, timeout=True, partial=True)

    assert metrics.snapshot() == {
        "requests": 2,
        "failures": 1,
        "timeouts": 1,
        "partial_outputs": 1,
        "failure_rate": 0.5,
        "timeout_rate": 0.5,
        "partial_output_rate": 0.5,
        "mean_latency_ms": 15.0,
    }
