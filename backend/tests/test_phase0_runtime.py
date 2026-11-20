"""Phase 0 grounding, runtime and security regressions."""

from __future__ import annotations

import sys
import types
from datetime import UTC, datetime

import pytest
from app.core.agent_loop.evidence import EvidenceAccounting, extract_evidence_facts
from app.core.agent_loop.publication import _NUMBER
from app.core.agent_loop.runtime import (
    _append_skipped_tool_results,
    _compact_model_history,
)
from app.core.instrument_resolution import InstrumentResolution
from app.models.request_models import Message
from app.models.routing import ExecutionMode
from app.observability.tracing import redact_trace_value
from app.security.policy import redact_secrets
from app.services.routing_policy import RoutingPolicy
from finai.session_runtime import _direct_tool_arguments


@pytest.mark.parametrize(
    "text", ["12bn", "5x", "20bps", "3Cr", "12k", "+5pp", "revenue of 12bn", "up 7%"]
)
def test_unit_suffixed_numbers_are_extracted(text: str) -> None:
    assert _NUMBER.findall(text)


@pytest.mark.parametrize("text", ["M&M rose", "NIFTY50 fell", "Q3 and FY26 results"])
def test_identifiers_do_not_match_number_regex(text: str) -> None:
    assert not _NUMBER.findall(text)


def _payload(instrument: str, close: float) -> dict[str, object]:
    return {
        "data": {"period": "1y", "interval": "1d", "latest": {"close": close}},
        "provenance": {
            "source": "fixture",
            "dataset": "prices",
            "instrument": instrument,
            "observed_at": datetime(2026, 9, 18, tzinfo=UTC).isoformat(),
            "ingested_at": datetime(2026, 9, 18, 0, 1, tzinfo=UTC).isoformat(),
            "version": "1",
            "quality_status": "verified",
        },
    }


def test_two_ticker_facts_do_not_overwrite() -> None:
    accounting = EvidenceAccounting()
    accounting.record_success("data:fetch_stock_data", _payload("AAA.NS", 1.0))
    accounting.record_success("data:fetch_stock_data", _payload("BBB.NS", 2.0))
    values = {
        f.instrument: f.value for f in accounting.facts.values() if "close" in f.fact_id
    }
    assert values == {"AAA.NS": 1.0, "BBB.NS": 2.0}
    assert accounting.invalid_evidence is False


def test_conflicting_fact_collision_fails_closed() -> None:
    accounting = EvidenceAccounting()
    accounting.record_success("data:fetch_stock_data", _payload("AAA.NS", 1.0))
    accounting.record_success("data:fetch_stock_data", _payload("AAA.NS", 9.0))
    assert accounting.invalid_evidence is True
    assert extract_evidence_facts(_payload("AAA.NS", 1.0))


def _call(call_id: str) -> dict[str, object]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": "x", "arguments": "{}"},
    }


def test_compaction_drops_assistant_with_its_tool_results() -> None:
    messages = [
        Message(role="user", content="q"),
        Message(role="assistant", content="", tool_calls=[_call("a"), _call("b")]),
        Message(role="tool", content="x" * 4000, tool_call_id="a"),
        Message(role="tool", content="y" * 4000, tool_call_id="b"),
        Message(role="user", content="more"),
    ]
    out = _compact_model_history(messages, 100)
    assert not any(m.role == "tool" for m in out)
    assert not any(m.tool_calls for m in out)


def test_skipped_tool_calls_get_synthetic_results() -> None:
    assistant = Message(
        role="assistant", content="", tool_calls=[_call("a"), _call("b")]
    )
    history = [assistant, Message(role="tool", content="ok", tool_call_id="a")]
    _append_skipped_tool_results(history, assistant)
    assert [m.tool_call_id for m in history if m.role == "tool"] == ["a", "b"]


def test_redaction_is_pattern_based_and_shared() -> None:
    value = {
        "access_token": "a",
        "x-api-key": "b",
        "HIVE_API_KEY": "c",
        "max_tokens": 5,
        "msg": "Bearer abc123 api_key=zzz",
    }
    for fn in (redact_secrets, redact_trace_value):
        out = fn(value)
        assert (
            out["access_token"]
            == out["x-api-key"]
            == out["HIVE_API_KEY"]
            == "[REDACTED]"
        )
        assert out["max_tokens"] == 5
        assert "abc123" not in out["msg"] and "zzz" not in out["msg"]


def test_tracing_banner_goes_to_stderr(monkeypatch, capsys) -> None:
    from app.observability import tracing

    def register(**_: object) -> object:
        print("Phoenix banner")
        return object()

    module = types.ModuleType("phoenix.otel")
    module.register = register  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "phoenix", types.ModuleType("phoenix"))
    monkeypatch.setitem(sys.modules, "phoenix.otel", module)
    monkeypatch.setattr(tracing.settings, "FINAI_OBSERVABILITY_ENABLED", True)
    monkeypatch.setattr(tracing, "_handle", tracing.TracingHandle(enabled=False))
    monkeypatch.setattr(tracing, "_instrument_httpx", lambda _p: None)
    tracing.initialize_tracing()
    captured = capsys.readouterr()
    assert "Phoenix banner" not in captured.out
    assert "Phoenix banner" in captured.err


@pytest.mark.parametrize(
    "query,direct",
    [
        ("price to earnings of TCS", False),
        ("what is the price to earnings ratio of TCS", False),
        ("price of TCS", True),
        ("what is the current price of INFY.NS", True),
        ("TCS share price", True),
    ],
)
@pytest.mark.asyncio
async def test_price_routing_is_imperative_only(query: str, direct: bool) -> None:
    route = await RoutingPolicy(None).decide(
        query, available_tools={"data:fetch_stock_data"}, available_skills=set()
    )
    assert (route.execution_mode is ExecutionMode.TOOL_ONLY) is direct


def test_direct_tool_arguments_use_resolver_not_tokens() -> None:
    route = types.SimpleNamespace(required_tools=["data:fetch_stock_data"])
    assert (
        _direct_tool_arguments(
            route,  # type: ignore[arg-type]
            "price of NSE",
        )
        is None
    )
    resolved = InstrumentResolution("resolved", ticker="TCS.NS")
    assert _direct_tool_arguments(
        route,  # type: ignore[arg-type]
        "price of TCS",
        resolved,
    ) == {"ticker": "TCS.NS"}


@pytest.mark.parametrize(
    "query,symbol",
    [
        ("price of TCS", "TCS"),
        ("what is the current price of M&M?", "M&M"),
        ("INFY quote", "INFY"),
    ],
)
def test_bare_nse_symbols_resolve_without_provider(query: str, symbol: str) -> None:
    from finai.session_runtime import _single_bare_symbol

    assert _single_bare_symbol(query) == symbol


def test_analytical_query_does_not_resolve_a_single_symbol() -> None:
    from finai.session_runtime import _single_bare_symbol

    assert _single_bare_symbol("price to earnings of TCS") is None
    assert _single_bare_symbol("price of NSE") is None
