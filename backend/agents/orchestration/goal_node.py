from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.core.orchestration_schemas import InteractivePlanPayload
from app.core.instrument_resolver import resolve_instruments
from app.core.contracts.graph_node import finalize_node_output
from app.core.node_resources import resources
from app.core.policies.json_parse_policy import parse_json_from_llm_response
from app.core.prompts import prompt_manager
from app.models.request_models import Message
from agents.shared.timeframe_policy import build_timeframe_policy, normalize_timeframe
from app.config.constants import MODEL_REASONING

_TICKER_PATTERN = re.compile(r"^[A-Z0-9]{1,20}(?:\.[A-Z]{1,4})?$")
_ALLOWED_RESEARCH_AGENTS = [
    "fundamental_analysis",
    "sentiment_analysis",
    "macro_analysis",
    "technical_analysis",
    "contrarian_analysis",
]


def _normalize_agents(candidates: list[Any]) -> list[str]:
    normalized: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        agent = candidate.strip()
        if agent in _ALLOWED_RESEARCH_AGENTS and agent not in normalized:
            normalized.append(agent)
    return normalized


def _default_agents() -> list[str]:
    return list(_ALLOWED_RESEARCH_AGENTS)


def _is_clarification_followup(
    conversation_history: list[dict[str, Any]], normalized_timeframe: str | None
) -> bool:
    if normalized_timeframe is None or not conversation_history:
        return False
    last_assistant_messages = [
        str(message.get("content", ""))
        for message in conversation_history[-4:]
        if isinstance(message, dict) and message.get("role") == "assistant"
    ]
    if not last_assistant_messages:
        return False
    recent_text = " ".join(last_assistant_messages).lower()
    return (
        "clarify" in recent_text
        or "what timeframe" in recent_text
        or ("timeframe" in recent_text and "scope" in recent_text)
    )


def _resolved_objective(
    query: str,
    conversation_history: list[dict[str, Any]],
    is_clarification_followup: bool,
) -> str:
    if not is_clarification_followup:
        return query

    for message in reversed(conversation_history):
        if not isinstance(message, dict):
            continue
        if message.get("role") != "user":
            continue
        content = str(message.get("content", "")).strip()
        if content:
            return content

    return query


async def _run_interactive_planner(
    query: str,
    conversation_history: list[dict[str, Any]],
) -> InteractivePlanPayload | None:
    system_prompt = prompt_manager.get_prompt(
        "autonomous_orchestrator.interactive_planner.system"
    )
    user_prompt = prompt_manager.get_prompt(
        "autonomous_orchestrator.interactive_planner.user", query=query
    )
    history_slice = conversation_history[-8:]

    planner_payload = {
        "query": query,
        "conversation_history": history_slice,
        "allowed_agents": _default_agents(),
        "response_schema": {
            "response_mode": "ask_clarification | ask_plan_approval | direct_execution",
            "assistant_response": "string",
            "proposed_timeframe": "string or null",
            "proposed_agents": ["string"],
            "is_fast_track": "boolean",
        },
        "rules": [
            "Return strict JSON only.",
            "Never return agent names outside allowed_agents.",
            "If timeframe is not explicit and user intent is broad, ask clarification.",
            "If user query already specifies timeframe and scope, use direct_execution.",
        ],
    }

    response = await resources.llm_service.generate_message(
        messages=[
            Message(role="system", content=system_prompt),
            Message(
                role="user",
                content=f"{user_prompt}\n\n{json.dumps(planner_payload, ensure_ascii=True)}",
            ),
        ],
        model=MODEL_REASONING,
    )
    parsed = parse_json_from_llm_response(getattr(response, "content", None))
    if not isinstance(parsed, dict):
        return None

    try:
        return InteractivePlanPayload.model_validate(parsed)
    except Exception:  # noqa: BLE001
        return None


def _normalize_ticker(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().upper()
    return candidate if _TICKER_PATTERN.match(candidate) else None


async def _resolve_ticker_with_llm(
    query: str,
    conversation_history: list[dict[str, Any]],
) -> tuple[str | None, list[str], dict[str, str | None]]:
    history_slice = conversation_history[-8:]
    system_prompt = prompt_manager.get_prompt(
        "autonomous_orchestrator.ticker_resolver.system"
    )

    prompt_payload = {
        "user_query": query,
        "conversation_history": history_slice,
        "task": "Extract candidate stock symbols or company names from context.",
        "output_schema": {
            "ticker": "string or null",
            "candidates": ["string"],
            "exchange_hint": "string or null",
            "segment_hint": "string or null",
            "instrument_type_hint": "string or null",
        },
        "rules": [
            "Return strict JSON only.",
            "If ambiguous or unresolved, set ticker to null and include best-effort candidates.",
            "Ticker format must be uppercase like AAPL or BRK.B.",
        ],
    }

    llm_response = await resources.llm_service.generate_message(
        messages=[
            Message(
                role="system",
                content=system_prompt,
            ),
            Message(role="user", content=json.dumps(prompt_payload, ensure_ascii=True)),
        ],
        model=MODEL_REASONING,
    )
    parsed_result = parse_json_from_llm_response(getattr(llm_response, "content", None))
    parsed: dict[str, Any] = parsed_result if isinstance(parsed_result, dict) else {}

    ticker = _normalize_ticker(parsed.get("ticker"))
    candidates_raw = parsed.get("candidates", [])
    candidates = [str(value).strip() for value in candidates_raw if str(value).strip()]
    if ticker and ticker not in candidates:
        candidates.insert(0, ticker)
    hints = {
        "exchange_hint": (
            str(parsed.get("exchange_hint")).strip().upper()
            if parsed.get("exchange_hint")
            else None
        ),
        "segment_hint": (
            str(parsed.get("segment_hint")).strip().upper()
            if parsed.get("segment_hint")
            else None
        ),
        "instrument_type_hint": (
            str(parsed.get("instrument_type_hint")).strip().lower()
            if parsed.get("instrument_type_hint")
            else None
        ),
    }
    return ticker, candidates, hints


async def goal_node(state: dict[str, Any]) -> dict[str, Any]:
    query = state.get("user_query", "")
    conversation_history = state.get("conversation_history", [])
    if not isinstance(conversation_history, list):
        conversation_history = []

    planner_payload: InteractivePlanPayload | None = None
    try:
        planner_payload = await _run_interactive_planner(query, conversation_history)
    except Exception:  # noqa: BLE001
        planner_payload = None

    planner_mode = (
        planner_payload.response_mode.strip().lower()
        if planner_payload is not None
        and isinstance(planner_payload.response_mode, str)
        else "direct_execution"
    )
    proposed_timeframe = (
        planner_payload.proposed_timeframe.strip().lower()
        if planner_payload is not None
        and isinstance(planner_payload.proposed_timeframe, str)
        else None
    )
    normalized_timeframe = normalize_timeframe(proposed_timeframe)
    proposed_agents = _normalize_agents(
        planner_payload.proposed_agents if planner_payload is not None else []
    )
    is_clarification_followup = _is_clarification_followup(
        conversation_history, normalized_timeframe
    )
    objective = _resolved_objective(
        query, conversation_history, is_clarification_followup
    )

    if planner_mode == "ask_clarification" or (
        proposed_timeframe is not None and normalized_timeframe is None
    ):
        prompt_text = (
            planner_payload.assistant_response
            if planner_payload is not None and planner_payload.assistant_response
            else "Please clarify your preferred timeframe and focus for this analysis."
        )
        payload = {
            "goal": None,
            "hypotheses": [],
            "plan_status": "awaiting_clarification",
            "timeframe": None,
            "timeframe_policy": {},
            "approved_agents": _default_agents(),
            "plan": {
                "response_mode": "ask_clarification",
                "assistant_response": prompt_text,
                "proposed_timeframe": None,
                "proposed_agents": _default_agents(),
                "is_fast_track": False,
            },
            "final_output": prompt_text,
            "final_report": prompt_text,
            "status": "success",
            "reasoning": "Awaiting timeframe clarification before executing analysis.",
            "confidence_score": 0.6,
            "next_action": "await_user_input",
            "data": {"plan_status": "awaiting_clarification"},
            "errors": [],
        }
        return finalize_node_output("goal_node", payload)

    if planner_mode == "ask_plan_approval" and not is_clarification_followup:
        prompt_text = (
            planner_payload.assistant_response
            if planner_payload is not None and planner_payload.assistant_response
            else "I drafted a plan. Please approve before execution."
        )
        approved_agents = proposed_agents or _default_agents()
        timeframe_policy = (
            build_timeframe_policy(normalized_timeframe)
            if normalized_timeframe is not None
            else {}
        )
        payload = {
            "goal": None,
            "hypotheses": [],
            "plan_status": "awaiting_approval",
            "timeframe": normalized_timeframe,
            "timeframe_policy": timeframe_policy,
            "approved_agents": approved_agents,
            "plan": {
                "response_mode": "ask_plan_approval",
                "assistant_response": prompt_text,
                "proposed_timeframe": normalized_timeframe,
                "proposed_agents": approved_agents,
                "is_fast_track": False,
            },
            "final_output": prompt_text,
            "final_report": prompt_text,
            "status": "success",
            "reasoning": "Awaiting user approval for the proposed analysis plan.",
            "confidence_score": 0.65,
            "next_action": "await_user_input",
            "data": {
                "plan_status": "awaiting_approval",
                "timeframe": normalized_timeframe,
            },
            "errors": [],
        }
        return finalize_node_output("goal_node", payload)

    ticker: str | None = None
    llm_candidates: list[str] = []
    resolution_hints: dict[str, str | None] = {
        "exchange_hint": None,
        "segment_hint": None,
        "instrument_type_hint": None,
    }
    try:
        ticker, llm_candidates, resolution_hints = await _resolve_ticker_with_llm(
            query, conversation_history
        )
    except Exception:  # noqa: BLE001
        ticker = None

    resolution = resolve_instruments(
        user_query=query,
        llm_candidates=llm_candidates,
        exchange_hint=resolution_hints.get("exchange_hint"),
        segment_hint=resolution_hints.get("segment_hint"),
        instrument_type_hint=resolution_hints.get("instrument_type_hint"),
    )
    if resolution.primary_instrument is not None:
        ticker = resolution.primary_instrument.trading_symbol

    instruments = [
        instrument.model_dump() for instrument in resolution.resolved_instruments
    ]

    goal = {
        "objective": objective,
        "scope": "financial_research",
        "constraints": ["no_hallucinated_data", "deterministic_scoring"],
        "success_criteria": "validated structured final output",
        "ticker": ticker,
        "instruments": instruments,
        "primary_instrument": (
            resolution.primary_instrument.model_dump()
            if resolution.primary_instrument
            else None
        ),
        "resolver_source": resolution.resolver_source,
        "ambiguous_candidates": resolution.ambiguous_candidates,
        "unresolved_entities": resolution.unresolved_entities,
        "ticker_extraction_status": "resolved" if ticker else "unresolved",
    }

    hypotheses = [
        {
            "id": "h1",
            "statement": "Price action and fundamentals jointly support a directional thesis.",
            "rationale": "Cross-validate market structure with fundamentals.",
            "priority": "P0",
        },
        {
            "id": "h2",
            "statement": "Macro and sentiment can invalidate the directional thesis.",
            "rationale": "Use macro and news to detect regime risk.",
            "priority": "P1",
        },
    ]
    timeframe_policy = (
        build_timeframe_policy(normalized_timeframe)
        if normalized_timeframe is not None
        else {}
    )

    payload = {
        "goal": goal,
        "hypotheses": hypotheses,
        "plan_status": "approved",
        "timeframe": normalized_timeframe,
        "timeframe_policy": timeframe_policy,
        "approved_agents": proposed_agents or _default_agents(),
        "plan": {
            "response_mode": planner_mode,
            "assistant_response": (
                planner_payload.assistant_response
                if planner_payload is not None
                else ""
            ),
            "proposed_timeframe": normalized_timeframe,
            "proposed_agents": proposed_agents or _default_agents(),
            "is_fast_track": (
                bool(planner_payload.is_fast_track)
                if planner_payload is not None
                else False
            ),
        },
        "status": "success",
        "reasoning": "Generated structured goal and hypotheses from user query.",
        "confidence_score": 0.7,
        "next_action": "run_data_check",
        "data": {"goal": goal, "hypotheses": hypotheses},
        "errors": [],
    }
    return finalize_node_output("goal_node", payload)
