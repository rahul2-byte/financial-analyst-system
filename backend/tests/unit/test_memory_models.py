from datetime import datetime

from storage.sql.memory_models import ErrorLog, InteractionLog, PerformanceMetric


def test_interaction_log_creation_sets_core_fields() -> None:
    log = InteractionLog(
        query_id="q1",
        input="test input",
        output="test output",
        score=0.85,
        retries=1,
        error_type="none",
    )

    assert log.query_id == "q1"
    assert log.score == 0.85
    assert log.retries == 1
    assert log.error_type == "none"
    assert log.correction_applied is None
    assert isinstance(log.timestamp, datetime)


def test_error_log_creation_sets_optional_details() -> None:
    log = ErrorLog(
        query_id="q1",
        error_type="hallucination",
        correction_applied="Do not guess",
        details="Used unverified data",
    )

    assert log.query_id == "q1"
    assert log.error_type == "hallucination"
    assert log.correction_applied == "Do not guess"
    assert log.details == "Used unverified data"
    assert isinstance(log.timestamp, datetime)


def test_performance_metric_creation_sets_timestamp() -> None:
    metric = PerformanceMetric(
        agent_name="synthesis",
        success_rate=0.9,
        average_score=0.88,
    )

    assert metric.agent_name == "synthesis"
    assert metric.success_rate == 0.9
    assert metric.average_score == 0.88
    assert isinstance(metric.timestamp, datetime)
