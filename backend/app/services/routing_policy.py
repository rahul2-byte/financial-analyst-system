from __future__ import annotations

import re
from typing import Any, Protocol

from app.models.routing import ExecutionMode, ModelTier, RoutePlan


class DecisionProvider(Protocol):
    async def decide(self, context: dict[str, Any]) -> RoutePlan: ...


_TICKER_LOOKUP = re.compile(
    r"\b(?:price|quote|close|latest price|current price)\b", re.IGNORECASE
)


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
    ) -> RoutePlan:
        normalized = normalized_query or query.strip()
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
                }
            )
            if route.confidence < self._min_confidence:
                return self._baseline_route(
                    normalized,
                    available_tools,
                    available_skills,
                    "low_router_confidence",
                )
            return route
        except Exception:  # noqa: BLE001 - router failure must use the safe baseline
            return self._baseline_route(
                normalized, available_tools, available_skills, "router_failure"
            )

    @staticmethod
    def _deterministic_route(
        query: str, available_tools: set[str], available_skills: set[str]
    ) -> RoutePlan | None:
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
