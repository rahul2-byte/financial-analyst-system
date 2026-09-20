from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelTier(StrEnum):
    NONE = "none"
    MAIN = "main"


class ExecutionMode(StrEnum):
    DETERMINISTIC = "deterministic"
    TOOL_ONLY = "tool_only"
    MODEL_ANSWER = "model_answer"
    REPORT_SYNTHESIS = "report_synthesis"
    REPAIR = "repair"
    ESCALATE = "escalate"


class RoutingContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=131_072)
    normalized_query: str = Field(min_length=1, max_length=131_072)
    available_tools: list[str] = Field(default_factory=list)
    available_skills: list[str] = Field(default_factory=list)
    evidence_status: dict[str, str] = Field(default_factory=dict)
    prior_failures: list[dict[str, Any]] = Field(default_factory=list, max_length=8)
    provider_health: dict[str, str] = Field(default_factory=dict)
    retry_budget_remaining: int = Field(default=1, ge=0)
    cost_budget_usd: float | None = Field(default=None, ge=0)


class RoutePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = "general_question"
    execution_mode: ExecutionMode = ExecutionMode.MODEL_ANSWER
    required_tools: list[str] = Field(default_factory=list)
    allowed_tools: set[str] = Field(default_factory=set)
    allowed_skills: set[str] = Field(default_factory=set)
    model_tier: ModelTier = ModelTier.MAIN
    selected_provider: str | None = None
    selected_model: str | None = None
    reason: str = ""
    reason_codes: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_main_model: bool = False
    fallback_policy: str = "baseline"
    retry_policy: str = "bounded"
    max_cost_usd: float | None = Field(default=None, ge=0)
    max_latency_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_tool_selection(self) -> RoutePlan:
        missing = set(self.required_tools) - self.allowed_tools
        if missing:
            raise ValueError(f"unknown required tool: {min(missing)}")
        if (
            self.execution_mode
            in {
                ExecutionMode.DETERMINISTIC,
                ExecutionMode.TOOL_ONLY,
            }
            and self.model_tier is not ModelTier.NONE
        ):
            raise ValueError("deterministic and tool-only routes cannot select a model")
        if self.requires_main_model and self.model_tier is not ModelTier.MAIN:
            raise ValueError("main-model routes must select the main tier")
        return self
