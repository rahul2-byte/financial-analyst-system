from __future__ import annotations

import json
import re
from typing import Any

from app.core.audit import build_node_audit_entry
from app.core.orchestration_schemas import InteractivePlanPayload
from app.core.instrument_resolver import resolve_instruments
from app.core.contracts.graph_node import finalize_node_output
from app.core.node_resources import resources
from app.core.observability import observe, opik_context
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


def _build_goal_audit(
    state: dict[str, Any],
    payload: dict[str, Any],
    *,
    goal: dict[str, Any] | None,
    planner_mode: str,
    proposed_timeframe: str | None,
    normalized_timeframe: str | None,
    approved_agents: list[str],
    is_clarification_followup: bool,
) -> dict[str, Any]:
    context_state = dict(state)
    context_state["goal"] = goal
    context_state["timeframe"] = normalized_timeframe
    audit = build_node_audit_entry("goal_node", context_state, payload)
    audit["decision_summary"] = {
        "planner_mode": planner_mode,
        "proposed_timeframe": proposed_timeframe,
        "normalized_timeframe": normalized_timeframe,
        "approved_agents": approved_agents,
        "ticker_resolution": (
            goal.get("ticker_extraction_status")
            if isinstance(goal, dict)
            else "unresolved"
        ),
        "resolver_source": (
            goal.get("resolver_source") if isinstance(goal, dict) else None
        ),
        "clarification_followup": is_clarification_followup,
    }
    return audit


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


def _is_broad_analysis_without_timeframe(
    query: str,
    normalized_timeframe: str | None,
    planner_mode: str,
) -> bool:
    if normalized_timeframe is not None or planner_mode != "direct_execution":
        return False
    lowered = query.lower()
    broad_terms = ["analyze", "analyse", "research", "deep dive", "full analysis"]
    subject_terms = ["stock", "company", "bank", "share"]
    return any(term in lowered for term in broad_terms) and any(
        term in lowered for term in subject_terms
    )


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


@observe(name="Research:GoalExtraction", as_type="span")
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

    conversation_history_dicts = [
        {"role": str(m.get("role")), "content": str(m.get("content"))}
        for m in conversation_history
        if isinstance(m, dict)
    ]
    is_clarification_followup = _is_clarification_followup(
        conversation_history_dicts, normalized_timeframe
    )
    objective = _resolved_objective(
        query, conversation_history_dicts, is_clarification_followup
    )

    opik_context.update_current_span(
        metadata={
            "proposed_timeframe": proposed_timeframe,
            "normalized_timeframe": normalized_timeframe,
            "proposed_agents": proposed_agents,
        }
    )

    if (
        planner_mode == "ask_clarification"
        or (proposed_timeframe is not None and normalized_timeframe is None)
        or _is_broad_analysis_without_timeframe(
            query,
            normalized_timeframe,
            planner_mode,
        )
    ):
        prompt_text = (
            planner_payload.assistant_response
            if planner_payload is not None and planner_payload.assistant_response
            else "Please clarify your preferred timeframe and focus for this analysis."
        )
        if _is_broad_analysis_without_timeframe(
            query, normalized_timeframe, planner_mode
        ):
            prompt_text = (
                "Please clarify your preferred timeframe and focus for this analysis."
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
        payload["data"]["audit"] = _build_goal_audit(
            state,
            payload,
            goal=None,
            planner_mode="ask_clarification",
            proposed_timeframe=proposed_timeframe,
            normalized_timeframe=None,
            approved_agents=_default_agents(),
            is_clarification_followup=is_clarification_followup,
        )
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
        payload["data"]["audit"] = _build_goal_audit(
            state,
            payload,
            goal=None,
            planner_mode="ask_plan_approval",
            proposed_timeframe=proposed_timeframe,
            normalized_timeframe=normalized_timeframe,
            approved_agents=approved_agents,
            is_clarification_followup=is_clarification_followup,
        )
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
            query, conversation_history_dicts
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
            "statement": f"Validate whether {objective} is supported by company fundamentals and earnings durability.",
            "rationale": "The planner should test company-specific drivers before relying on narrative synthesis.",
            "priority": "P0",
        },
        {
            "id": "h2",
            "statement": f"Identify whether price action, market narrative, macro regime, or sector conditions could invalidate {objective}.",
            "rationale": "The planner should search for disconfirming qualitative and macro evidence, not just confirming evidence.",
            "priority": "P1",
        },
        {
            "id": "h3",
            "statement": f"Look for a credible contrarian case against the prevailing interpretation of {objective}.",
            "rationale": "The planner should reserve a second-wave challenge step for consensus-risk review.",
            "priority": "P2",
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
    payload["data"]["audit"] = _build_goal_audit(
        state,
        payload,
        goal=goal,
        planner_mode=planner_mode,
        proposed_timeframe=proposed_timeframe,
        normalized_timeframe=normalized_timeframe,
        approved_agents=payload["approved_agents"],
        is_clarification_followup=is_clarification_followup,
    )
    return finalize_node_output("goal_node", payload)
