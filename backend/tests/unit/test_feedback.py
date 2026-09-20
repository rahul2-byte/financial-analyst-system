from app.observability.feedback import summarize_run


def test_run_summary_exposes_route_and_failure_context() -> None:
    summary = summarize_run(
        [
            {
                "type": "route.decision.made",
                "execution_mode": "report_synthesis",
                "model_tier": "main",
                "confidence": 0.91,
                "reason_codes": ["jev_route"],
                "required_tools": [],
            },
            {
                "type": "provider.failed",
                "provider": "hive",
                "model_id": "glm",
                "phase": "stream",
                "message": "timeout",
            },
            {
                "type": "run.completed",
                "terminal_status": "completed_with_limited_evidence",
            },
        ]
    )

    assert summary["route"]["model_tier"] == "main"
    assert summary["failure_context"][0]["category"] == "provider_failure"
    assert summary["correctness_status"] == "completed_with_limited_evidence"
