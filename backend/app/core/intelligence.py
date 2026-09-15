from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, ClassVar, Protocol


class IntelligenceAction(str, Enum):
    RETRY = "run_research_plan"
    TERMINATE_SUCCESS = "terminate_success"
    TERMINATE_FAILURE = "terminate_failure"


@dataclass(frozen=True)
class EvaluationFeedback:
    score: float
    error_type: str
    feedback: str


@dataclass(frozen=True)
class IntelligenceDecision:
    action: IntelligenceAction
    normalized_score: float
    error_type: str
    feedback: str
    retry_count: int
    correction_prompt: str | None
    strategy_update: dict[str, Any]


class MemoryStore(Protocol):
    def log_interaction(
        self,
        *,
        query_id: str,
        input: str,
        output: str,
        score: float,
        retries: int,
        error_type: str | None,
        correction_applied: str | None = None,
    ) -> None: ...

    def log_error(
        self,
        *,
        query_id: str,
        error_type: str,
        correction_applied: str,
        details: str | None = None,
    ) -> None: ...

    def record_performance_metric(
        self,
        *,
        agent_name: str,
        success_rate: float,
        average_score: float,
    ) -> None: ...

    def get_recent_interactions(self, limit: int = 20) -> list[dict[str, Any]]: ...


class SystemIntelligenceLayer:
    _PROMPT_MAP: ClassVar[dict[str, str]] = {
        "hallucination": "Do not guess. Use only verifiable facts from the data context.",
        "incomplete_response": "Provide a complete and detailed answer addressing all parts of the user query.",
        "factual_error": "Correct factual mismatches and use only grounded values from deterministic sources.",
        "formatting_error": "Return output that strictly follows the required schema and formatting contract.",
        "reasoning_error": "Explain step-by-step reasoning and ensure every conclusion follows from the evidence.",
        "unsafe_output": "Remove unsafe claims, guarantees, and unsupported recommendations.",
    }

    def __init__(
        self,
        memory_store: MemoryStore | None = None,
        *,
        max_retries: int = 3,
        pass_threshold: float = 0.8,
    ) -> None:
        self._memory_store = memory_store
        self.max_retries = max_retries
        self.pass_threshold = pass_threshold

    def normalize_score(self, score: float) -> float:
        return max(0.0, min(1.0, float(score)))

    def classify_error(self, error_type: str | None, feedback: str | None) -> str:
        normalized = (error_type or "").strip().lower()
        if normalized in self._PROMPT_MAP or normalized == "none":
            return normalized

        text = (feedback or "").lower()
        if any(token in text for token in ("hallucinat", "unsupported", "made up")):
            return "hallucination"
        if any(token in text for token in ("incomplete", "missing", "not covered")):
            return "incomplete_response"
        if any(token in text for token in ("format", "schema", "json")):
            return "formatting_error"
        if any(token in text for token in ("reason", "logic", "inconsistent")):
            return "reasoning_error"
        if any(token in text for token in ("unsafe", "guarantee", "advice")):
            return "unsafe_output"
        if any(token in text for token in ("factual", "incorrect", "wrong")):
            return "factual_error"
        return "reasoning_error"

    def _failure_pressure(self, error_type: str) -> int:
        if self._memory_store is None:
            return 0
        history = self._memory_store.get_recent_interactions(limit=20)
        return sum(1 for item in history if item.get("error_type") == error_type)

    def _build_strategy_update(
        self, error_type: str, failure_pressure: int
    ) -> dict[str, Any]:
        temperature = 0.2
        constraints: list[str] = []
        model_override: str | None = None

        if error_type == "hallucination":
            temperature = 0.1
            constraints.append("grounded_only")
        elif error_type == "incomplete_response":
            temperature = 0.25
            constraints.append("expand_coverage")
        elif error_type == "formatting_error":
            temperature = 0.05
            constraints.append("strict_schema")
        elif error_type == "reasoning_error":
            temperature = 0.15
            constraints.append("stepwise_reasoning")
        elif error_type == "unsafe_output":
            temperature = 0.05
            constraints.append("safe_output_only")
            model_override = "safety_hardened"

        return {
            "temperature": temperature,
            "constraints": constraints,
            "model_override": model_override,
            "failure_pressure": failure_pressure,
        }

    def evaluate_and_adapt(
        self,
        evaluation: EvaluationFeedback,
        *,
        current_retries: int,
    ) -> IntelligenceDecision:
        normalized_score = self.normalize_score(evaluation.score)
        error_type = self.classify_error(evaluation.error_type, evaluation.feedback)
        failure_pressure = self._failure_pressure(error_type)
        strategy_update = self._build_strategy_update(error_type, failure_pressure)

        if normalized_score >= self.pass_threshold and error_type == "none":
            return IntelligenceDecision(
                action=IntelligenceAction.TERMINATE_SUCCESS,
                normalized_score=normalized_score,
                error_type=error_type,
                feedback=evaluation.feedback,
                retry_count=current_retries,
                correction_prompt=None,
                strategy_update=strategy_update,
            )

        if current_retries >= self.max_retries:
            return IntelligenceDecision(
                action=IntelligenceAction.TERMINATE_FAILURE,
                normalized_score=normalized_score,
                error_type=error_type,
                feedback=evaluation.feedback,
                retry_count=current_retries,
                correction_prompt=None,
                strategy_update=strategy_update,
            )

        return IntelligenceDecision(
            action=IntelligenceAction.RETRY,
            normalized_score=normalized_score,
            error_type=error_type,
            feedback=evaluation.feedback,
            retry_count=current_retries + 1,
            correction_prompt=self._PROMPT_MAP.get(
                error_type,
                "Improve response quality while staying grounded in available evidence.",
            ),
            strategy_update=strategy_update,
        )

    def process_evaluation(
        self,
        *,
        query_id: str,
        user_input: str,
        candidate_output: str,
        evaluation: EvaluationFeedback,
        current_retries: int,
        agent_name: str,
    ) -> IntelligenceDecision:
        decision = self.evaluate_and_adapt(
            evaluation,
            current_retries=current_retries,
        )

        if self._memory_store is not None:
            self._memory_store.log_interaction(
                query_id=query_id,
                input=user_input,
                output=candidate_output,
                score=decision.normalized_score,
                retries=decision.retry_count,
                error_type=decision.error_type,
                correction_applied=decision.correction_prompt,
            )
            if (
                decision.error_type != "none"
                and decision.action != IntelligenceAction.TERMINATE_SUCCESS
            ):
                self._memory_store.log_error(
                    query_id=query_id,
                    error_type=decision.error_type,
                    correction_applied=decision.correction_prompt or "none",
                    details=decision.feedback,
                )
            self._memory_store.record_performance_metric(
                agent_name=agent_name,
                success_rate=(
                    1.0
                    if decision.action == IntelligenceAction.TERMINATE_SUCCESS
                    else 0.0
                ),
                average_score=decision.normalized_score,
            )

        return decision

    def as_payload(self, decision: IntelligenceDecision) -> dict[str, Any]:
        payload = asdict(decision)
        payload["action"] = decision.action.value
        return payload
