from app.core.intelligence import (
    EvaluationFeedback,
    IntelligenceAction,
    SystemIntelligenceLayer,
)


class _MockMemoryStore:
    def __init__(self) -> None:
        self.interactions: list[dict[str, object]] = []
        self.errors: list[dict[str, object]] = []
        self.metrics: list[dict[str, object]] = []
        self.history: list[dict[str, object]] = []

    def log_interaction(self, **payload):
        self.interactions.append(payload)

    def log_error(self, **payload):
        self.errors.append(payload)

    def record_performance_metric(self, **payload):
        self.metrics.append(payload)

    def get_recent_interactions(self, limit: int = 20):
        return self.history[-limit:]


def test_evaluate_and_adapt_passes_when_score_is_above_threshold() -> None:
    sil = SystemIntelligenceLayer(max_retries=3, pass_threshold=0.8)

    decision = sil.evaluate_and_adapt(
        EvaluationFeedback(score=0.91, error_type="none", feedback="looks good"),
        current_retries=1,
    )

    assert decision.action == IntelligenceAction.TERMINATE_SUCCESS
    assert decision.normalized_score == 0.91
    assert decision.retry_count == 1
    assert decision.correction_prompt is None


def test_evaluate_and_adapt_retries_with_hallucination_correction() -> None:
    sil = SystemIntelligenceLayer(max_retries=3, pass_threshold=0.8)

    decision = sil.evaluate_and_adapt(
        EvaluationFeedback(
            score=0.4,
            error_type="hallucination",
            feedback="contains unsupported claims",
        ),
        current_retries=1,
    )

    assert decision.action == IntelligenceAction.RETRY
    assert decision.retry_count == 2
    assert decision.error_type == "hallucination"
    assert "verifiable facts" in (decision.correction_prompt or "")
    assert decision.strategy_update["temperature"] < 0.3


def test_evaluate_and_adapt_stops_at_retry_limit() -> None:
    sil = SystemIntelligenceLayer(max_retries=3, pass_threshold=0.8)

    decision = sil.evaluate_and_adapt(
        EvaluationFeedback(
            score=0.25,
            error_type="reasoning_error",
            feedback="reasoning is inconsistent",
        ),
        current_retries=3,
    )

    assert decision.action == IntelligenceAction.TERMINATE_FAILURE
    assert decision.retry_count == 3
    assert decision.correction_prompt is None


def test_classify_error_uses_feedback_when_error_type_is_unknown() -> None:
    sil = SystemIntelligenceLayer()

    error_type = sil.classify_error(
        "unknown", "The answer is incomplete and misses risks"
    )

    assert error_type == "incomplete_response"


def test_high_score_with_explicit_error_still_triggers_retry() -> None:
    sil = SystemIntelligenceLayer(max_retries=3, pass_threshold=0.8)

    decision = sil.evaluate_and_adapt(
        EvaluationFeedback(
            score=0.95,
            error_type="formatting_error",
            feedback="schema violation persists",
        ),
        current_retries=0,
    )

    assert decision.action == IntelligenceAction.RETRY
    assert decision.error_type == "formatting_error"


def test_process_evaluation_logs_feedback_and_learning_metrics() -> None:
    store = _MockMemoryStore()
    store.history = [
        {"score": 0.3, "error_type": "hallucination"},
        {"score": 0.45, "error_type": "hallucination"},
    ]
    sil = SystemIntelligenceLayer(memory_store=store, max_retries=3, pass_threshold=0.8)

    decision = sil.process_evaluation(
        query_id="q-1",
        user_input="Analyze HDFCBANK",
        candidate_output="Unsupported claim",
        evaluation=EvaluationFeedback(
            score=0.4,
            error_type="hallucination",
            feedback="unsupported claim present",
        ),
        current_retries=0,
        agent_name="synthesis",
    )

    assert decision.action == IntelligenceAction.RETRY
    assert len(store.interactions) == 1
    assert len(store.errors) == 1
    assert len(store.metrics) == 1
    assert store.errors[0]["error_type"] == "hallucination"
    assert decision.strategy_update["failure_pressure"] == 2
