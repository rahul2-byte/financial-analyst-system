from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import uuid4

import httpx
from app.core.logging import get_logger
from app.core.model_call_trace import ModelCallTrace, safe_endpoint
from app.core.prompts import PromptRegistry
from app.models.routing import (
    ExecutionMode,
    ModelTier,
    NextAction,
    PromptInjectionRisk,
    RoutePlan,
)


class JevProviderError(RuntimeError):
    """A bounded failure from the Jev decision provider."""


logger = get_logger(__name__)


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
        ModelTier.MAIN,
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
    "deny": (
        "unsafe_request",
        ExecutionMode.DENY,
        ModelTier.NONE,
        [],
    ),
}


class JevService:
    """OpenRouter Jev client for typed route decisions."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://openrouter.ai/api/alpha/decisions",
        model: str = "~typesafe/jev-latest",
        timeout_seconds: float = 10.0,
        max_retries: int = 1,
        client: httpx.AsyncClient | None = None,
        prompts: PromptRegistry | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = client or httpx.AsyncClient()
        self.prompts = prompts or PromptRegistry.bundled()

    async def decide(self, context: dict[str, Any]) -> RoutePlan:
        if not self.api_key:
            raise JevProviderError("OPENROUTER_API_KEY is not configured")
        payload = {
            "model": self.model,
            "state": _minimize_context(context),
            "questions": {
                "route": {
                    "type": "choice",
                    "instructions": self.prompts.get("jev.route.instructions"),
                    "criteria": {
                        key: self.prompts.get(f"jev.route.criteria.{key}")
                        for key in (
                            "tool_market",
                            "tool_fundamentals",
                            "tool_technical",
                            "tool_news",
                            "small_answer",
                            "mid_repair",
                            "report",
                            "clarify",
                            "deny",
                        )
                    },
                }
            },
        }
        trace = ModelCallTrace.create(
            provider="openrouter_jev",
            model=self.model,
            run_id=str(context["run_id"]) if context.get("run_id") else None,
            conversation_id=(
                str(_conversation_id(context)) if _conversation_id(context) else None
            ),
            call_id=str(uuid4()),
        )
        started = time.perf_counter()
        if trace is not None:
            trace.write("call.started", {"operation": "route"})
        for attempt in range(self.max_retries + 1):
            attempt_started = time.perf_counter()
            try:
                if trace is not None:
                    trace.write(
                        "request.attempt",
                        {
                            "attempt": attempt + 1,
                            "endpoint": safe_endpoint(self.base_url),
                            "request_body": payload,
                        },
                    )
                response = await self._client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                if response.status_code in {429, 529} and attempt < self.max_retries:
                    if trace is not None:
                        trace.write(
                            "request.retrying",
                            {
                                "attempt": attempt + 1,
                                "attempt_duration_ms": round(
                                    (time.perf_counter() - attempt_started) * 1000, 2
                                ),
                                "status_code": response.status_code,
                                "response_body": response.text,
                            },
                        )
                    await asyncio.sleep(min(0.1 * (2**attempt), 0.5))
                    continue
                response.raise_for_status()
                response_payload = response.json()
                route = _route_from_response(
                    response_payload, context, model=self.model
                )
                if trace is not None:
                    trace.write(
                        "call.completed",
                        {
                            "operation": "route",
                            "duration_ms": round(
                                (time.perf_counter() - started) * 1000, 2
                            ),
                            "attempt_duration_ms": round(
                                (time.perf_counter() - attempt_started) * 1000, 2
                            ),
                            "attempt": attempt + 1,
                            "status_code": response.status_code,
                            "response": response_payload,
                            "route": route.model_dump(mode="json"),
                        },
                    )
                return route
            except httpx.TransportError as exc:
                if trace is not None:
                    trace.write(
                        "request.failed",
                        {
                            "attempt": attempt + 1,
                            "attempt_duration_ms": round(
                                (time.perf_counter() - attempt_started) * 1000, 2
                            ),
                            "error_type": type(exc).__name__,
                        },
                    )
                if attempt < self.max_retries:
                    continue
                if trace is not None:
                    trace.write(
                        "call.failed",
                        {
                            "operation": "route",
                            "duration_ms": round(
                                (time.perf_counter() - started) * 1000, 2
                            ),
                            "attempt_duration_ms": round(
                                (time.perf_counter() - attempt_started) * 1000, 2
                            ),
                            "attempt": attempt + 1,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                raise JevProviderError(
                    f"Jev transport failure: {type(exc).__name__}"
                ) from exc
            except httpx.HTTPStatusError as exc:
                if trace is not None:
                    trace.write(
                        "call.failed",
                        {
                            "operation": "route",
                            "duration_ms": round(
                                (time.perf_counter() - started) * 1000, 2
                            ),
                            "attempt_duration_ms": round(
                                (time.perf_counter() - attempt_started) * 1000, 2
                            ),
                            "attempt": attempt + 1,
                            "status_code": exc.response.status_code,
                            "response_body": exc.response.text,
                            "error_type": type(exc).__name__,
                        },
                    )
                raise JevProviderError(
                    f"Jev HTTP failure: {exc.response.status_code}"
                ) from exc
            except (KeyError, TypeError, ValueError) as exc:
                if trace is not None:
                    trace.write(
                        "call.failed",
                        {
                            "operation": "route",
                            "duration_ms": round(
                                (time.perf_counter() - started) * 1000, 2
                            ),
                            "attempt_duration_ms": round(
                                (time.perf_counter() - attempt_started) * 1000, 2
                            ),
                            "attempt": attempt + 1,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                raise JevProviderError(f"Jev response invalid: {exc}") from exc
            except JevProviderError as exc:
                if trace is not None:
                    trace.write(
                        "call.failed",
                        {
                            "operation": "route",
                            "duration_ms": round(
                                (time.perf_counter() - started) * 1000, 2
                            ),
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                raise
        raise JevProviderError("Jev retry budget exhausted")

    async def review_output(self, context: dict[str, Any]) -> NextAction:
        if not self.api_key:
            raise JevProviderError("OPENROUTER_API_KEY is not configured")
        payload = {
            "model": self.model,
            "state": _minimize_context({**context, "phase": "output_review"}),
            "questions": {
                "review": {
                    "type": "choice",
                    "instructions": self.prompts.get("jev.review.instructions"),
                    "criteria": {
                        key: self.prompts.get(f"jev.review.criteria.{key}")
                        for key in ("accept", "repair_output", "escalate_model", "deny")
                    },
                }
            },
        }
        trace = ModelCallTrace.create(
            provider="openrouter_jev",
            model=self.model,
            run_id=str(context["run_id"]) if context.get("run_id") else None,
            conversation_id=(
                str(_conversation_id(context)) if _conversation_id(context) else None
            ),
        )
        started = time.perf_counter()
        attempt_started = started
        if trace is not None:
            trace.write("call.started", {"operation": "output_review"})
            trace.write(
                "request.attempt",
                {
                    "attempt": 1,
                    "endpoint": safe_endpoint(self.base_url),
                    "request_body": payload,
                },
            )
        try:
            response = await self._client.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            response_payload = response.json()
            choice = str(
                response_payload.get("answers", {}).get("review", {}).get("choice", "")
            )
            if choice == "accept":
                result = NextAction.GENERATE_TEXT
            else:
                try:
                    result = NextAction(choice)
                except ValueError as exc:
                    raise JevProviderError(
                        f"unknown Jev review: {choice or '<missing>'}"
                    ) from exc
            if trace is not None:
                trace.write(
                    "call.completed",
                    {
                        "operation": "output_review",
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                        "attempt_duration_ms": round(
                            (time.perf_counter() - attempt_started) * 1000, 2
                        ),
                        "attempt": 1,
                        "status_code": response.status_code,
                        "response": response_payload,
                        "action": result.value,
                    },
                )
            return result
        except BaseException as exc:
            if trace is not None:
                trace.write(
                    "call.failed",
                    {
                        "operation": "output_review",
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                        "attempt_duration_ms": round(
                            (time.perf_counter() - attempt_started) * 1000, 2
                        ),
                        "attempt": 1,
                        "status_code": getattr(
                            getattr(exc, "response", None), "status_code", None
                        ),
                        "response_body": getattr(
                            getattr(exc, "response", None), "text", None
                        ),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
            raise


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
        "phase": str(context.get("phase", "input")),
        "prompt_injection_risk": str(
            context.get("prompt_injection_risk", PromptInjectionRisk.LOW)
        ),
        "risk_flags": [str(item) for item in context.get("risk_flags", [])],
        "conversation_context": _bounded_conversation_context(
            context.get("conversation_context")
        ),
        "evidence_sufficient": context.get("evidence_sufficient"),
        "output": str(context.get("output", ""))[:4000],
    }


def _conversation_id(context: dict[str, Any]) -> Any:
    nested = context.get("conversation_context")
    if isinstance(nested, dict):
        return context.get("conversation_id") or nested.get("conversation_id")
    return context.get("conversation_id")


def _bounded_conversation_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    recent = value.get("recent_messages")
    messages = recent if isinstance(recent, list) else []
    return {
        "is_follow_up": bool(value.get("is_follow_up", False)),
        "resolved_entities": [
            str(item)[:120] for item in value.get("resolved_entities", [])
        ][:16],
        "recent_messages": [
            {
                "role": str(item.get("role", "")),
                "content": str(item.get("content", ""))[:2_000],
            }
            for item in messages[-12:]
            if isinstance(item, dict)
        ],
        "estimated_tokens": int(value.get("estimated_tokens", 0)),
    }


def _route_from_response(
    payload: dict[str, Any], context: dict[str, Any], *, model: str
) -> RoutePlan:
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
    next_action = {
        ExecutionMode.TOOL_ONLY: NextAction.TOOL_ONLY,
        ExecutionMode.REPORT_SYNTHESIS: NextAction.GENERATE_TEXT,
        ExecutionMode.MODEL_ANSWER: NextAction.GENERATE_TEXT,
        ExecutionMode.REPAIR: NextAction.REPAIR_OUTPUT,
        ExecutionMode.ESCALATE: NextAction.ESCALATE_MODEL,
        ExecutionMode.DETERMINISTIC: NextAction.ASK_CLARIFICATION,
        ExecutionMode.DENY: NextAction.DENY,
    }[execution_mode]
    return RoutePlan(
        intent=intent,
        execution_mode=execution_mode,
        required_tools=required_tools,
        allowed_tools=route_tools,
        allowed_skills={str(item) for item in context.get("available_skills", [])},
        model_tier=tier,
        selected_provider="openrouter",
        selected_model=model,
        reason=f"Jev selected {choice}.",
        reason_codes=["jev_route"],
        confidence=float(confidence),
        requires_main_model=tier is ModelTier.MAIN,
        next_action=next_action,
        prompt_injection_risk=PromptInjectionRisk(
            str(context.get("prompt_injection_risk", PromptInjectionRisk.LOW))
        ),
        risk_flags=[str(item) for item in context.get("risk_flags", [])],
        evidence_sufficient=context.get("evidence_sufficient"),
    )
