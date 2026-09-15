from __future__ import annotations

import json
from typing import Any

from app.config.constants import MODEL_REASONING
from app.core.model_stream import get_captured_token_sink, publish_public_tokens
from app.core.prompts import prompt_manager
from app.models.request_models import Message

_VALIDATED_REPORT_AGENTS = (
    "fundamental_analysis",
    "technical_analysis",
    "macro_analysis",
    "sentiment_analysis",
    "contrarian_analysis",
)


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=True, default=str, indent=2)


def _selected_validated_agent_outputs(results: dict[str, Any]) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for agent_name in _VALIDATED_REPORT_AGENTS:
        value = results.get(agent_name)
        if value:
            selected[agent_name] = value
    return selected


def _low_confidence_disclaimer(reason: str | None) -> str:
    explanation = (
        reason.strip()
        if isinstance(reason, str) and reason.strip()
        else (
            "This report is best-effort and should be treated with caution because the system terminated in a low-confidence state."
        )
    )
    return (
        "> [!WARNING]\n> Low confidence research report.\n> "
        + explanation.replace("\n", "\n> ")
        + "\n\n"
    )


def _evidence_disclaimer(data_status: Any) -> str:
    if not isinstance(data_status, dict):
        return ""
    incomplete = [
        (str(dataset), status)
        for dataset, status in data_status.items()
        if isinstance(status, dict) and status.get("status") != "available"
    ]
    if not incomplete:
        return ""

    lines = [
        "> [!WARNING]",
        "> Partial evidence coverage.",
        "> This report uses the data that was available and excludes unsupported calculations.",
    ]
    for dataset, status in incomplete:
        state = str(status.get("status") or "unavailable")
        detail = status.get("error_code") or status.get("error") or "coverage incomplete"
        lines.append(f"> - {dataset}: {state} ({detail})")
    return "\n".join(lines) + "\n\n"


async def generate_narrative_report(
    state: dict[str, Any],
    resources: Any,
    *,
    terminal_output: dict[str, Any] | None = None,
    is_low_confidence: bool = False,
    reason: str | None = None,
) -> str:
    results = state.get("results", {})
    synthesis = results.get("synthesis", {})
    if not isinstance(synthesis, dict):
        synthesis = {}

    final_output = terminal_output if isinstance(terminal_output, dict) else {}
    terminal_status = str(
        final_output.get("status") or state.get("status") or "unknown"
    )
    terminal_reason = (
        reason or final_output.get("reasoning") or state.get("reasoning") or ""
    )

    validated_agent_outputs = _selected_validated_agent_outputs(
        results if isinstance(results, dict) else {}
    )
    evidence_status = _stringify(state.get("data_status", {}))

    system_prompt = prompt_manager.get_prompt("report.system")
    user_prompt = prompt_manager.get_prompt(
        "report.user",
        user_query=str(state.get("user_query", "")),
        terminal_status=terminal_status,
        terminal_reason=str(terminal_reason),
        structured_synthesis=_stringify(synthesis),
        validated_agent_outputs=_stringify(validated_agent_outputs),
        evidence_status=evidence_status,
    )

    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_prompt),
    ]
    sink = get_captured_token_sink()
    if sink:
        with publish_public_tokens():
            response = await resources.llm_service.generate_message(
                messages=messages,
                model=MODEL_REASONING,
            )
    else:
        response = await resources.llm_service.generate_message(
            messages=messages,
            model=MODEL_REASONING,
        )
    report_text = (getattr(response, "content", "") or "").strip()
    if not report_text:
        report_text = "# Executive Summary\n\nValidated research was available, but the final narrative report could not be rendered. Refer to the structured output panel for the verified result."

    disclaimer = _evidence_disclaimer(state.get("data_status"))
    if is_low_confidence or terminal_status == "low_confidence":
        disclaimer = _low_confidence_disclaimer(str(terminal_reason)) + disclaimer
    return disclaimer + report_text
