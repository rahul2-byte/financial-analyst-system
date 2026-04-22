"""Research planner node."""

from __future__ import annotations

from typing import Any

from agents.financial.research.evidence_policy import (
    AGENT_PRIORITIES,
    build_qualitative_requirements,
    build_structured_requirements,
    dependencies_for_agent,
    derive_required_dimensions,
    dimensions_for_agent,
    missing_dimensions_for_agent,
)
from agents.financial.research.query_derivation import (
    derive_agent_objective,
    derive_research_question,
)
from agents.shared.utils import extract_goal_symbols, selected_agents, task_sort_key
from app.core.audit import build_node_audit_entry
from app.core.contracts.graph_node import finalize_node_output
from app.core.research_plan_schemas import ResearchTaskSpec


def _task_parameters(task: ResearchTaskSpec, query: str) -> dict[str, Any]:
    return {
        "ticker": task.ticker,
        "symbols": list(task.symbols),
        "query": query,
        "timeframe": task.timeframe,
        "objective": task.objective,
        "research_question": task.research_question,
        "required_dimensions": list(task.required_dimensions),
        "missing_dimensions": list(task.missing_dimensions),
        "verification_focus": task.verification_focus,
        "correction_prompt": task.correction_prompt,
    }


def _build_task(
    agent: str,
    ticker: str | None,
    symbols: list[str],
    query: str,
    timeframe: str | None,
    hypotheses: list[dict[str, Any]],
    data_status: dict[str, Any],
    correction_prompt: str | None,
    verification_focus: str | None,
) -> ResearchTaskSpec:
    required_dimensions = dimensions_for_agent(
        agent,
        derive_required_dimensions(query, hypotheses),
    )
    missing_dimensions = missing_dimensions_for_agent(
        agent, required_dimensions, data_status
    )
    objective = derive_agent_objective(
        agent,
        ticker,
        query,
        timeframe,
        hypotheses,
        correction_prompt,
    )
    research_question = derive_research_question(
        agent,
        ticker,
        query,
        timeframe,
        objective,
        missing_dimensions,
        correction_prompt,
    )
    task = ResearchTaskSpec(
        task_id=agent,
        agent=agent,
        priority=AGENT_PRIORITIES.get(agent, "P2"),
        ticker=ticker,
        symbols=symbols,
        timeframe=timeframe,
        objective=objective,
        research_question=research_question,
        required_dimensions=required_dimensions,
        missing_dimensions=missing_dimensions,
        depends_on=dependencies_for_agent(agent),
        structured_requirements=build_structured_requirements(agent),
        qualitative_requirements=build_qualitative_requirements(
            agent, research_question
        ),
        verification_focus=verification_focus,
        correction_prompt=correction_prompt,
    )
    task.parameters = _task_parameters(task, query)
    return task


async def research_plan_node(state: dict[str, Any]) -> dict[str, Any]:
    goal = dict(state.get("goal", {}))
    extracted = extract_goal_symbols(goal)
    raw_ticker = goal.get("ticker")
    if isinstance(raw_ticker, str) and raw_ticker.strip():
        ticker = raw_ticker.strip().upper()
    else:
        ticker = extracted[0] if extracted else None
    symbols = [ticker] if isinstance(ticker, str) and ticker.strip() else []
    query = str(state.get("user_query", ""))
    timeframe = state.get("timeframe")
    selected = selected_agents(state)
    hypotheses = list(state.get("hypotheses", []))
    data_status = dict(state.get("data_status", {}))
    correction_prompt = state.get("correction_prompt")

    tasks: list[dict[str, Any]] = []
    replan_lookup = {
        task.get("agent"): task
        for task in state.get("replanned_tasks", [])
        if isinstance(task, dict) and isinstance(task.get("agent"), str)
    }

    for agent in selected:
        replanned = replan_lookup.get(agent, {})
        parameters = dict(replanned.get("parameters", {}))
        verification_focus = parameters.get("verification_focus")
        effective_correction_prompt = (
            parameters.get("correction_prompt") or correction_prompt
        )
        task = _build_task(
            agent=agent,
            ticker=ticker,
            symbols=symbols,
            query=query,
            timeframe=timeframe,
            hypotheses=hypotheses,
            data_status=data_status,
            correction_prompt=(
                str(effective_correction_prompt)
                if effective_correction_prompt is not None
                else None
            ),
            verification_focus=(
                str(verification_focus) if verification_focus is not None else None
            ),
        )
        if isinstance(replanned.get("priority"), str):
            task.priority = replanned["priority"]
        task.parameters = _task_parameters(task, query)
        tasks.append(task.model_dump(mode="json"))

    tasks = sorted(tasks, key=task_sort_key)
    reset_results = {"synthesis": None}
    for agent in selected:
        reset_results[agent] = None
    payload = {
        "tasks": tasks,
        "task_contexts": {},
        "results": reset_results,
        "critic_decision": None,
        "claim_verification": None,
        "validation_passed": False,
        "evaluation_passed": False,
        "evaluation_result": {},
        "final_output": None,
        "final_report": None,
        "force_replan": False,
        "replanned_tasks": [],
        "status": "success",
        "reasoning": "Built validated, agent-specific research tasks from the user goal and evidence gaps.",
        "confidence_score": float(state.get("confidence_score", 0.6)),
        "next_action": "run_research_context",
        "data": {"tasks": tasks},
        "errors": [],
    }

    assigned_agents = [t.get("agent") for t in tasks if "agent" in t]
    dimensions_by_agent = {
        t.get("agent"): t.get("required_dimensions", []) for t in tasks if "agent" in t
    }
    dependencies_by_task = {
        str(t.get("task_id")): list(t.get("depends_on", []))
        for t in tasks
        if isinstance(t, dict) and t.get("task_id")
    }
    verification_focus_by_task = {
        str(t.get("task_id")): t.get("verification_focus")
        for t in tasks
        if isinstance(t, dict) and t.get("task_id")
    }
    audit = build_node_audit_entry("research_plan_node", state, payload)
    audit["decision_summary"] = {
        "assigned_agents": assigned_agents,
        "task_count": len(tasks),
        "task_ids": [str(t.get("task_id")) for t in tasks if isinstance(t, dict)],
        "dimensions_by_agent": dimensions_by_agent,
        "dependencies_by_task": dependencies_by_task,
        "verification_focus_by_task": verification_focus_by_task,
        "correction_prompt_present": bool(correction_prompt),
    }
    payload["data"]["audit"] = audit

    return finalize_node_output("research_plan_node", payload)
