from __future__ import annotations

import asyncio
from typing import Any

import httpx
from app.models.routing import ExecutionMode, ModelTier, RoutePlan


class JevProviderError(RuntimeError):
    """A bounded failure from the Jev decision provider."""


_ROUTES: dict[str, tuple[str, ExecutionMode, ModelTier, list[str]]] = {
    "tool_market": (
        "market_lookup",
        ExecutionMode.TOOL_ONLY,
        ModelTier.NONE,
        ["data:fetch_stock_data"],
    ),
    "tool_fundamentals": (
        "fundamentals_lookup",
        ExecutionMode.TOOL_ONLY,
        ModelTier.NONE,
        ["data:fetch_fundamentals"],
    ),
    "tool_technical": (
        "technical_lookup",
        ExecutionMode.TOOL_ONLY,
        ModelTier.NONE,
        ["analysis:get_technical_overview"],
    ),
    "tool_news": (
        "news_lookup",
        ExecutionMode.TOOL_ONLY,
        ModelTier.NONE,
        ["news:fetch_news"],
    ),
    "small_answer": (
        "general_question",
        ExecutionMode.MODEL_ANSWER,
        ModelTier.SMALL,
        [],
    ),
    "mid_repair": (
        "repair",
        ExecutionMode.REPAIR,
        ModelTier.MID,
        [],
    ),
    "report": (
        "research_report",
        ExecutionMode.REPORT_SYNTHESIS,
        ModelTier.MAIN,
        [],
    ),
    "clarify": (
        "clarification",
        ExecutionMode.DETERMINISTIC,
        ModelTier.NONE,
        ["interaction:ask_user"],
    ),
}


class JevService:
    """Direct TypeSafe Jev client for typed route decisions."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.typesafe.ai",
        model: str = "jev-latest",
        timeout_seconds: float = 0.75,
        max_retries: int = 1,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = client or httpx.AsyncClient()

    async def decide(self, context: dict[str, Any]) -> RoutePlan:
        if not self.api_key:
            raise JevProviderError("TYPESAFE_API_KEY is not configured")
        payload = {
            "model": self.model,
            "state": _minimize_context(context),
            "questions": {
                "route": {
                    "type": "choice",
                    "instructions": (
                        "Choose the narrowest safe FIN-AI execution route. "
                        "Use report only when verified evidence must be synthesized."
                    ),
                    "criteria": {
                        "tool_market": "A direct current or historical market lookup is sufficient.",
                        "tool_fundamentals": "A direct fundamentals lookup is sufficient.",
                        "tool_technical": "A direct technical overview lookup is sufficient.",
                        "tool_news": "A direct recent news lookup is sufficient.",
                        "small_answer": "A short non-report answer needs a small model.",
                        "mid_repair": "A structured repair or compact transformation is needed.",
                        "report": "Multiple verified sources require a full research report.",
                        "clarify": "The request lacks information needed to act safely.",
                    },
                }
            },
        }
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.post(
                    f"{self.base_url}/v1/systemone",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                if response.status_code in {429, 529} and attempt < self.max_retries:
                    await asyncio.sleep(min(0.1 * (2**attempt), 0.5))
                    continue
                response.raise_for_status()
                return _route_from_response(response.json(), context)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < self.max_retries:
                    continue
                raise JevProviderError(
                    f"Jev transport failure: {type(exc).__name__}"
                ) from exc
            except httpx.HTTPStatusError as exc:
                raise JevProviderError(
                    f"Jev HTTP failure: {exc.response.status_code}"
                ) from exc
            except (KeyError, TypeError, ValueError) as exc:
                raise JevProviderError(f"Jev response invalid: {exc}") from exc
        raise JevProviderError("Jev retry budget exhausted")


def _minimize_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": str(context.get("query", ""))[:4000],
        "normalized_query": str(context.get("normalized_query", ""))[:4000],
        "available_tools": sorted(
            str(item) for item in context.get("available_tools", [])
        ),
        "available_skills": sorted(
            str(item) for item in context.get("available_skills", [])
        ),
        "evidence_status": dict(context.get("evidence_status") or {}),
        "prior_failures": list(context.get("prior_failures") or [])[-8:],
        "provider_health": dict(context.get("provider_health") or {}),
    }


def _route_from_response(payload: dict[str, Any], context: dict[str, Any]) -> RoutePlan:
    answer = payload.get("answers", {}).get("route", {})
    choice = str(answer.get("choice", ""))
    if choice not in _ROUTES:
        raise JevProviderError(f"unknown Jev route: {choice or '<missing>'}")
    intent, execution_mode, tier, required_tools = _ROUTES[choice]
    available = {str(item) for item in context.get("available_tools", [])}
    missing = set(required_tools) - available
    if missing:
        raise JevProviderError(f"Jev selected unavailable tool: {min(missing)}")
    probabilities = answer.get("probabilities") or {}
    confidence = answer.get("confidence")
    if confidence is None:
        confidence = probabilities.get(choice, 0.0)
    route_tools = (
        available
        if execution_mode is ExecutionMode.REPORT_SYNTHESIS
        else set(required_tools)
    )
    return RoutePlan(
        intent=intent,
        execution_mode=execution_mode,
        required_tools=required_tools,
        allowed_tools=route_tools,
        allowed_skills={str(item) for item in context.get("available_skills", [])},
        model_tier=tier,
        selected_provider=str(payload.get("provider"))
        if payload.get("provider")
        else None,
        selected_model=str(payload.get("model")) if payload.get("model") else None,
        reason=f"Jev selected {choice}.",
        reason_codes=["jev_route"],
        confidence=float(confidence),
        requires_main_model=tier is ModelTier.MAIN,
    )
