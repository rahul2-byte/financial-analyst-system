from __future__ import annotations

import re
from typing import Any, Protocol

from app.core.guardrails import assess_input_safety
from app.core.logging import get_logger
from app.models.routing import ExecutionMode, ModelTier, NextAction, RoutePlan

logger = get_logger(__name__)


class DecisionProvider(Protocol):
    async def decide(self, context: dict[str, Any]) -> RoutePlan: ...

    async def review_output(self, context: dict[str, Any]) -> NextAction: ...


_TICKER_LOOKUP = re.compile(
    r"\b(?:price|quote|close|latest price|current price)\b", re.IGNORECASE
)
_MARKET_STATUS_LOOKUP = re.compile(
    r"\b(?:market status|market open|market closed|is\s+(?:nse|bse)\s+(?:open|closed)|pre[- ]open|holiday)\b",
    re.IGNORECASE,
)
_MARKET_HOLIDAY_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


class RoutingPolicy:
    """Deterministic preflight with an optional typed Jev decision provider."""

    def __init__(
        self, jev: DecisionProvider | None, min_confidence: float = 0.60
    ) -> None:
        self._jev = jev
        self._min_confidence = min_confidence

    async def decide(
        self,
        query: str,
        *,
        available_tools: set[str],
        available_skills: set[str],
        normalized_query: str | None = None,
        evidence_status: dict[str, str] | None = None,
        prior_failures: list[dict[str, Any]] | None = None,
        provider_health: dict[str, str] | None = None,
        phase: str = "input",
        conversation_context: dict[str, Any] | None = None,
    ) -> RoutePlan:
        normalized = normalized_query or query.strip()
        safety = assess_input_safety(normalized)
        if safety.risk.value == "high":
            return RoutePlan(
                intent="unsafe_request",
                execution_mode=ExecutionMode.DENY,
                model_tier=ModelTier.NONE,
                reason="The request contains multiple high-risk instruction patterns.",
                reason_codes=["deterministic_injection_guard"],
                confidence=1.0,
                next_action="deny",
                prompt_injection_risk=safety.risk,
                risk_flags=safety.flags,
            )
        deterministic = self._deterministic_route(
            normalized, available_tools, available_skills
        )
        if deterministic is not None:
            return deterministic
        if self._jev is None:
            return self._baseline_route(
                normalized, available_tools, available_skills, "router_unavailable"
            )
        try:
            route = await self._jev.decide(
                {
                    "query": query,
                    "normalized_query": normalized,
                    "available_tools": sorted(available_tools),
                    "available_skills": sorted(available_skills),
                    "evidence_status": evidence_status or {},
                    "prior_failures": prior_failures or [],
                    "provider_health": provider_health or {},
                    "phase": phase,
                    "prompt_injection_risk": safety.risk.value,
                    "risk_flags": safety.flags,
                    "conversation_context": conversation_context or {},
                }
            )
            if route.confidence < self._min_confidence:
                return self._baseline_route(
                    normalized,
                    available_tools,
                    available_skills,
                    "low_router_confidence",
                )
            if (
                route.next_action is NextAction.ASK_CLARIFICATION
                and conversation_context
                and conversation_context.get("resolved_ticker")
                and conversation_context.get("comparison_intent")
            ):
                return route.model_copy(
                    update={
                        "intent": "research_report",
                        "execution_mode": ExecutionMode.REPORT_SYNTHESIS,
                        "required_tools": [],
                        "allowed_tools": available_tools,
                        "allowed_skills": available_skills,
                        "model_tier": ModelTier.MAIN,
                        "requires_main_model": True,
                        "next_action": NextAction.GENERATE_TEXT,
                        "reason": "Deterministic conversation context resolved the comparison.",
                        "reason_codes": [
                            *route.reason_codes,
                            "context_default_applied",
                            "jev_clarification_overridden",
                        ],
                    }
                )
            return route
        except Exception as exc:  # noqa: BLE001 - router failure must use the safe baseline
            logger.warning("Jev routing failed: %s", type(exc).__name__)
            return self._baseline_route(
                normalized, available_tools, available_skills, "router_failure"
            )

    async def review_output(self, context: dict[str, Any]) -> NextAction:
        if self._jev is None or not hasattr(self._jev, "review_output"):
            return NextAction.GENERATE_TEXT
        try:
            return await self._jev.review_output(context)
        except Exception:  # noqa: BLE001 - output review must fail open to bounded code
            return NextAction.GENERATE_TEXT

    @staticmethod
    def _deterministic_route(
        query: str, available_tools: set[str], available_skills: set[str]
    ) -> RoutePlan | None:
        if (
            _MARKET_HOLIDAY_DATE.search(query)
            and "holiday" in query.casefold()
            and "data:fetch_market_holidays" in available_tools
        ):
            return RoutePlan(
                intent="market_holiday",
                execution_mode=ExecutionMode.TOOL_ONLY,
                required_tools=["data:fetch_market_holidays"],
                allowed_tools={"data:fetch_market_holidays"},
                allowed_skills=available_skills,
                model_tier=ModelTier.NONE,
                reason="The request is a direct market holiday lookup.",
                reason_codes=["deterministic_operation", "market_holiday_tool"],
                confidence=1.0,
            )
        if _MARKET_STATUS_LOOKUP.search(query) and "data:fetch_market_status" in available_tools:
            return RoutePlan(
                intent="market_status",
                execution_mode=ExecutionMode.TOOL_ONLY,
                required_tools=["data:fetch_market_status"],
                allowed_tools={"data:fetch_market_status"},
                allowed_skills=available_skills,
                model_tier=ModelTier.NONE,
                reason="The request is a direct market status lookup.",
                reason_codes=["deterministic_operation", "market_state_tool"],
                confidence=1.0,
            )
        if _TICKER_LOOKUP.search(query) and "data:fetch_stock_data" in available_tools:
            return RoutePlan(
                intent="market_lookup",
                execution_mode=ExecutionMode.TOOL_ONLY,
                required_tools=["data:fetch_stock_data"],
                allowed_tools={"data:fetch_stock_data"},
                allowed_skills=available_skills,
                model_tier=ModelTier.NONE,
                reason="The request is a direct market lookup.",
                reason_codes=["deterministic_operation", "direct_tool_sufficient"],
                confidence=1.0,
            )
        return None

    @staticmethod
    def _baseline_route(
        query: str,
        available_tools: set[str],
        available_skills: set[str],
        reason_code: str,
    ) -> RoutePlan:
        report = any(
            marker in query.casefold()
            for marker in (
                "report",
                "investment thesis",
                "full analysis",
                "detailed analysis",
            )
        ) or query.casefold().startswith(
            ("analyze ", "analyse ", "research ", "compare ")
        )
        return RoutePlan(
            intent="research_report" if report else "general_question",
            execution_mode=(
                ExecutionMode.REPORT_SYNTHESIS if report else ExecutionMode.MODEL_ANSWER
            ),
            allowed_tools=available_tools,
            allowed_skills=available_skills,
            model_tier=ModelTier.MAIN,
            reason="The existing bounded AgentLoop is the safe fallback.",
            reason_codes=[reason_code],
            confidence=0.0,
            requires_main_model=True,
        )
