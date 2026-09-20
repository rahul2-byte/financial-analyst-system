from __future__ import annotations

from typing import Any

from app.security.policy import redact_secrets


def summarize_run(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Build compact, redacted route feedback from one persisted run."""
    route: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []
    terminal_status = "unknown"
    model_calls = 0
    for event in events:
        event_type = event.get("type")
        if event_type == "route.decision.made":
            route = {
                key: event.get(key)
                for key in (
                    "intent",
                    "execution_mode",
                    "model_tier",
                    "confidence",
                    "reason_codes",
                    "required_tools",
                    "reason",
                    "selected_provider",
                    "selected_model",
                )
            }
        elif event_type == "model.request.started":
            model_calls += 1
        elif event_type == "run.completed":
            terminal_status = str(event.get("terminal_status", "unknown"))
        elif event_type == "run.failed":
            terminal_status = "failed"
            failures.append(
                {
                    "category": str(event.get("category", "runtime_failure")),
                    "message": str(redact_secrets(event.get("message", "")))[:256],
                }
            )
        elif event_type == "provider.failed":
            failures.append(
                {
                    "category": "provider_failure",
                    "provider": event.get("provider"),
                    "model": event.get("model_id"),
                    "phase": event.get("phase"),
                    "message": str(redact_secrets(event.get("message", "")))[:256],
                }
            )
        elif event_type == "tool.failed":
            failures.append(
                {
                    "category": "tool_failure",
                    "tool": event.get("tool"),
                    "message": str(redact_secrets(event.get("message", "")))[:256],
                }
            )
    return {
        "route": route,
        "model_calls": model_calls,
        "failure_context": failures[-8:],
        "correctness_status": terminal_status,
        "regression_candidate": bool(failures)
        or terminal_status in {"failed", "partial"},
    }
