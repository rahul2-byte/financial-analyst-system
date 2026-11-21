"""Report check, fact check, and safety review run as a bounded retry pipeline."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from app.core.agent_loop import AgentLoop, AgentLoopConfig
from app.core.agent_loop import runtime as runtime_module
from app.models.request_models import Message
from app.models.routing import NextAction

FACT = "prices:ABC.NS:data.latest.close"
TOOL_CALL = {
    "index": 0,
    "id": "call-stage",
    "type": "function",
    "function": {"name": "data:fetch_stock_data", "arguments": '{"ticker":"ABC"}'},
}


class _Tools:
    def definitions(self) -> list[dict]:
        return [{"type": "function", "function": {"name": "data:fetch_stock_data"}}]

    async def execute(self, name: str, arguments: dict) -> dict:
        del name, arguments
        return {
            "success": True,
            "data": {"latest": {"close": 123.4}},
            "provenance": {
                "source": "fixture",
                "dataset": "prices",
                "instrument": "ABC.NS",
                "observed_at": "2026-09-18T00:00:00+00:00",
                "ingested_at": "2026-09-18T00:01:00+00:00",
                "version": "fixture-1",
                "quality_status": "verified",
                "source_url": "https://fixture.example",
            },
        }


def _draft(
    prose: str = f"Close [[fact:{FACT}]].", refs: list[str] | None = None
) -> str:
    return json.dumps(
        {
            "executive_summary": prose,
            "key_drivers": ["Price evidence returned."],
            "detailed_analysis": prose,
            "risks": ["Coverage is limited."],
            "final_view": "Review.",
            "claims": [
                {
                    "claim_id": "c1",
                    "text": f"Close [[fact:{FACT}]].",
                    "importance": "major",
                    "evidence_refs": ["src"],
                    "numeric_refs": [FACT] if refs is None else refs,
                }
            ],
            "citations": [{"citation_id": "src", "source_id": "prices"}],
        }
    )


GOOD = _draft()
WRONG_NUMBER = _draft("The price was 123.4 and 99 last week.")
BAD_CONTRACT = "not json at all"


class _Model:
    def __init__(self, drafts: list[str], on_draft: Any = None) -> None:
        self.drafts = list(drafts)
        self.calls: list[list[Message]] = []
        self.on_draft = on_draft

    def generate_stream(self, messages: list[Message], model: str, **kwargs: Any):
        del model, kwargs
        self.calls.append(list(messages))
        first = len(self.calls) == 1

        async def stream() -> Any:
            if first:
                yield {
                    "event": "chunk",
                    "data": {"choices": [{"delta": {"tool_calls": [TOOL_CALL]}}]},
                }
            else:
                yield {"event": "token", "data": self.drafts.pop(0)}
                if self.on_draft:
                    self.on_draft()

        return stream()


class _Reviewer:
    review_available = True

    def __init__(self, verdicts: list[NextAction]) -> None:
        self.verdicts = list(verdicts)
        self.reviewed: list[str] = []

    async def review_output(self, context: dict[str, Any]) -> NextAction:
        self.reviewed.append(str(context.get("output")))
        return self.verdicts.pop(0) if self.verdicts else NextAction.GENERATE_TEXT


async def _run(
    model: _Model, *, provider: Any = None, **config: Any
) -> tuple[AgentLoop, list[Any]]:
    loop = AgentLoop(
        model,
        _Tools(),
        config=AgentLoopConfig(
            publish_reports=True, decision_provider=provider, **config
        ),
    )
    messages = [Message(role="user", content="report on ABC")]
    events = [e async for e in loop.run(messages, conversation_id=uuid4())]
    return loop, events


def _stages(events: list[Any]) -> list[tuple[str, bool, bool]]:
    return [(e.stage, e.passed, e.retrying) for e in events if e.type == "check.stage"]


def _text(events: list[Any]) -> str:
    return "".join(e.text for e in events if e.type == "response.delta")


def test_wrong_number_fails_fact_check_then_repairs_and_publishes() -> None:
    model = _Model([WRONG_NUMBER, GOOD])
    loop, events = asyncio.run(_run(model))

    repair = model.calls[-1][-1]
    assert repair.prompt_key == "publication.report_repair"
    assert 'stage "Fact check"' in repair.content
    assert '"123.4"' in repair.content
    assert f"matching fact: {FACT}" in repair.content
    assert "numeric_claim_unbound" in repair.content
    assert events[-1].terminal_status == "completed"
    assert f"{123.4}" in _text(events)
    assert _stages(events) == [
        ("report_check", True, True),
        ("fact_check", False, True),
        ("report_check", True, False),
        ("fact_check", True, False),
    ]
    failed = next(e for e in events if e.type == "check.stage" and not e.passed)
    assert failed.attempt == 1 and failed.max_attempts == 2
    assert failed.reasons == ["2 unsupported number(s)"]
    assert loop.last_report_result["publication_status"] == "passed"
    assert [s["stage"] for s in loop.last_report_result["stages"]].count(
        "fact_check"
    ) == 2


def test_report_check_failure_then_success() -> None:
    model = _Model([BAD_CONTRACT, GOOD])
    _, events = asyncio.run(_run(model))

    assert 'stage "Report check"' in model.calls[-1][-1].content
    assert events[-1].terminal_status == "completed"
    assert _stages(events) == [
        ("report_check", False, True),
        ("report_check", True, False),
        ("fact_check", True, False),
    ]


def test_structured_reports_are_not_sent_to_the_reviewer() -> None:
    reviewer = _Reviewer([NextAction.DENY, NextAction.REPAIR_OUTPUT])
    model = _Model([GOOD])
    _, events = asyncio.run(_run(model, provider=reviewer))

    assert reviewer.reviewed == []
    assert events[-1].terminal_status == "completed"
    assert _stages(events) == [
        ("report_check", True, False),
        ("fact_check", True, False),
    ]
    assert all(e.stage != "safety_review" for e in events if e.type == "check.stage")


def test_unknown_fact_ids_are_listed_in_repair_details() -> None:
    bad_id = "prices:ABC.NS:data.latest.volume"
    bad = _draft(f"Close [[fact:{FACT}]] and [[fact:{bad_id}]].")
    model = _Model([bad, GOOD])
    _, events = asyncio.run(_run(model))

    repair = model.calls[-1][-1].content
    assert bad_id in repair
    assert "Use only fact IDs from the catalog" in repair
    assert events[-1].terminal_status == "completed"


def test_exhaustion_falls_back_and_names_failing_stage() -> None:
    model = _Model([WRONG_NUMBER, WRONG_NUMBER, WRONG_NUMBER])
    loop, events = asyncio.run(_run(model, max_report_repairs=2))

    text = _text(events)
    assert len(model.calls) == 4  # tool call, draft, two repairs
    assert events[-1].terminal_status == "completed_with_limited_evidence"
    assert "deterministic provider observations" in text
    limits = text.split("## Data limitations", 1)[1]
    assert "Fact check failed after repair attempts: 2 unsupported number(s)" in limits
    last = [e for e in events if e.type == "check.stage"][-1]
    assert (last.stage, last.passed, last.retrying, last.attempt) == (
        "fact_check",
        False,
        False,
        2,
    )
    assert loop.last_report_result["publication_status"] == "failed"


def test_no_retry_starts_past_the_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    base = time.perf_counter()
    clock = SimpleNamespace(now=base)
    monkeypatch.setattr(
        runtime_module, "time", SimpleNamespace(perf_counter=lambda: clock.now)
    )
    model = _Model(
        [WRONG_NUMBER, GOOD], on_draft=lambda: setattr(clock, "now", base + 500.0)
    )
    _, events = asyncio.run(_run(model, max_run_seconds=150.0))

    assert len(model.calls) == 2  # no repair call after the deadline
    assert events[-1].terminal_status == "completed_with_limited_evidence"
    assert "Fact check failed after repair attempts" in _text(events)
    assert not any(e.type == "check.stage" and e.retrying for e in events)


def test_stage_events_are_ordered_and_sequenced() -> None:
    _, events = asyncio.run(_run(_Model([WRONG_NUMBER, GOOD])))

    stages = [e for e in events if e.type == "check.stage"]
    sequences = [e.meta.sequence for e in stages]
    assert sequences == sorted(sequences)
    assert [e.label for e in stages[:2]] == ["Report check", "Fact check"]
    first_draft_end = next(i for i, e in enumerate(events) if e.type == "check.stage")
    assert all(e.type != "response.delta" for e in events[:first_draft_end])
    assert events[-1].type == "run.completed"


def test_cli_renders_stage_lines() -> None:
    from finai.plain import render_event

    _, events = asyncio.run(_run(_Model([WRONG_NUMBER, GOOD])))
    lines = [render_event(e).strip() for e in events if e.type == "check.stage"]

    assert lines[0] == "✓ Report check"
    assert lines[1] == "✗ Fact check — 2 unsupported number(s), retrying (1/2)"
    assert lines[-1] == "✓ Fact check"
