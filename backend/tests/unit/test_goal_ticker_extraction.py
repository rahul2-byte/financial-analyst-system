import pytest

from app.core.instrument_resolver import ResolutionResult, ResolvedInstrument
from agents.orchestration.goal_node import goal_node
from app.core.node_resources import resources


class _StubLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _StubLLMService:
    def __init__(self, content: str | list[str]) -> None:
        if isinstance(content, list):
            self.contents = list(content)
        else:
            self.contents = [content]
        self.last_messages = None
        self.call_count = 0

    async def generate_message(self, messages, model, tools=None):
        self.last_messages = messages
        index = min(self.call_count, len(self.contents) - 1)
        self.call_count += 1
        return _StubLLMResponse(self.contents[index])


def _set_stub_llm(stub_llm: _StubLLMService):
    previous = resources._llm_service
    setattr(resources, "_llm_service", stub_llm)
    return previous


def _patch_resolver(monkeypatch, ticker: str | None):
    def _stub_resolver(
        user_query,
        llm_candidates,
        limit_per_candidate=5,
        exchange_hint=None,
        segment_hint=None,
        instrument_type_hint=None,
    ):
        if not ticker:
            return ResolutionResult(
                resolved_instruments=[],
                primary_instrument=None,
                ambiguous_candidates=[],
                unresolved_entities=[],
                resolver_source="db_lookup",
            )
        instrument = ResolvedInstrument(
            instrument_key=f"NSE_EQ|{ticker}",
            trading_symbol=ticker,
            exchange="NSE",
            segment="EQ",
            instrument_type="equity",
            underlying_symbol=ticker,
            company_name=ticker,
        )
        return ResolutionResult(
            resolved_instruments=[instrument],
            primary_instrument=instrument,
            ambiguous_candidates=[],
            unresolved_entities=[],
            resolver_source="db_lookup",
        )

    monkeypatch.setattr(
        "agents.orchestration.goal_node.resolve_instruments", _stub_resolver
    )


@pytest.mark.asyncio
async def test_goal_passes_llm_hints_to_resolver(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def _stub_resolver(
        user_query,
        llm_candidates,
        limit_per_candidate=5,
        exchange_hint=None,
        segment_hint=None,
        instrument_type_hint=None,
    ):
        captured["exchange_hint"] = exchange_hint
        captured["segment_hint"] = segment_hint
        captured["instrument_type_hint"] = instrument_type_hint
        return ResolutionResult(
            resolved_instruments=[],
            primary_instrument=None,
            ambiguous_candidates=[],
            unresolved_entities=[],
            resolver_source="db_lookup",
        )

    monkeypatch.setattr(
        "agents.orchestration.goal_node.resolve_instruments", _stub_resolver
    )

    stub_llm = _StubLLMService(
        '{"ticker":null,"candidates":["AAPL"],"exchange_hint":"NSE","segment_hint":"EQ","instrument_type_hint":"equity"}'
    )
    previous = _set_stub_llm(stub_llm)

    try:
        await goal_node(
            {"user_query": "Analyze Apple on NSE", "conversation_history": []}
        )
    finally:
        setattr(resources, "_llm_service", previous)

    assert captured["exchange_hint"] == "NSE"
    assert captured["segment_hint"] == "EQ"
    assert captured["instrument_type_hint"] == "equity"


@pytest.mark.asyncio
async def test_goal_extracts_company_alias_ticker_not_stopword(monkeypatch) -> None:
    _patch_resolver(monkeypatch, "RELIANCE.NS")
    stub_llm = _StubLLMService('{"ticker": "RELIANCE.NS"}')
    previous = _set_stub_llm(stub_llm)

    try:
        result = await goal_node({"user_query": "Research Reliance for 5 years"})
    finally:
        setattr(resources, "_llm_service", previous)

    assert result["goal"]["ticker"] == "RELIANCE.NS"
    assert result["goal"]["ticker_extraction_status"] == "resolved"


@pytest.mark.asyncio
async def test_goal_extracts_symbol_token(monkeypatch) -> None:
    _patch_resolver(monkeypatch, "AAPL")
    stub_llm = _StubLLMService('{"ticker": "AAPL"}')
    previous = _set_stub_llm(stub_llm)

    try:
        result = await goal_node({"user_query": "Is AAPL a good trade?"})
    finally:
        setattr(resources, "_llm_service", previous)

    assert result["goal"]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_goal_handles_dot_symbol_token(monkeypatch) -> None:
    _patch_resolver(monkeypatch, "BRK.B")
    stub_llm = _StubLLMService('{"ticker": "BRK.B"}')
    previous = _set_stub_llm(stub_llm)

    try:
        result = await goal_node({"user_query": "Should I buy BRK.B now?"})
    finally:
        setattr(resources, "_llm_service", previous)

    assert result["goal"]["ticker"] == "BRK.B"


@pytest.mark.asyncio
async def test_goal_returns_none_when_query_has_no_ticker(monkeypatch) -> None:
    _patch_resolver(monkeypatch, None)
    stub_llm = _StubLLMService('{"ticker": null}')
    previous = _set_stub_llm(stub_llm)

    try:
        result = await goal_node(
            {"user_query": "What are the macro risks over next quarter?"}
        )
    finally:
        setattr(resources, "_llm_service", previous)

    assert result["goal"]["ticker"] is None


@pytest.mark.asyncio
async def test_goal_uses_conversation_history_for_ticker_resolution(
    monkeypatch,
) -> None:
    _patch_resolver(monkeypatch, "AAPL")
    stub_llm = _StubLLMService('{"ticker": "AAPL"}')
    previous = _set_stub_llm(stub_llm)

    try:
        await goal_node(
            {
                "user_query": "Analyze this company for me",
                "conversation_history": [
                    {"role": "user", "content": "I meant Apple, not Microsoft."}
                ],
            }
        )
    finally:
        setattr(resources, "_llm_service", previous)

    assert stub_llm.last_messages is not None
    prompt_payload = stub_llm.last_messages[-1].content
    assert "Apple" in prompt_payload


@pytest.mark.asyncio
async def test_goal_requests_clarification_when_query_is_vague(monkeypatch) -> None:
    _patch_resolver(monkeypatch, None)
    stub_llm = _StubLLMService(
        '{"response_mode":"ask_clarification","assistant_response":"What timeframe should I use?","proposed_timeframe":null,"proposed_agents":[],"is_fast_track":false}'
    )
    previous = _set_stub_llm(stub_llm)

    try:
        result = await goal_node({"user_query": "Analyze Apple"})
    finally:
        setattr(resources, "_llm_service", previous)

    assert result["plan_status"] == "awaiting_clarification"
    assert isinstance(result["final_output"], str)
    assert "timeframe" in result["final_output"].lower()


@pytest.mark.asyncio
async def test_goal_rejects_direct_execution_for_broad_query_without_timeframe(
    monkeypatch,
) -> None:
    _patch_resolver(monkeypatch, "HDFCBANK")
    stub_llm = _StubLLMService(
        [
            '{"response_mode":"direct_execution","assistant_response":"Executing now.","proposed_timeframe":null,"proposed_agents":["fundamental_analysis","technical_analysis","sentiment_analysis","macro_analysis","contrarian_analysis"],"is_fast_track":true}',
            '{"ticker":"HDFCBANK"}',
        ]
    )
    previous = _set_stub_llm(stub_llm)

    try:
        result = await goal_node({"user_query": "Analyse the HDFC stock"})
    finally:
        setattr(resources, "_llm_service", previous)

    assert result["plan_status"] == "awaiting_clarification"
    assert result["timeframe"] is None
    assert "timeframe" in result["final_output"].lower()


@pytest.mark.asyncio
async def test_goal_requests_approval_for_semiclear_query(monkeypatch) -> None:
    _patch_resolver(monkeypatch, "AAPL")
    stub_llm = _StubLLMService(
        [
            '{"response_mode":"ask_plan_approval","assistant_response":"I can run a 5Y multi-factor analysis using fundamental, sentiment, and macro agents. Approve?","proposed_timeframe":"5y","proposed_agents":["fundamental_analysis","sentiment_analysis","macro_analysis"],"is_fast_track":false}',
            '{"ticker":"AAPL"}',
        ]
    )
    previous = _set_stub_llm(stub_llm)

    try:
        result = await goal_node({"user_query": "Analyze AAPL with full context"})
    finally:
        setattr(resources, "_llm_service", previous)

    assert result["plan_status"] == "awaiting_approval"
    assert result["timeframe"] == "5y"
    assert result["approved_agents"] == [
        "fundamental_analysis",
        "sentiment_analysis",
        "macro_analysis",
    ]
    assert isinstance(result["final_output"], str)
    assert "approve" in result["final_output"].lower()


@pytest.mark.asyncio
async def test_goal_fast_track_executes_without_waiting(monkeypatch) -> None:
    _patch_resolver(monkeypatch, "AAPL")
    stub_llm = _StubLLMService(
        [
            '{"response_mode":"direct_execution","assistant_response":"Executing now.","proposed_timeframe":"5y","proposed_agents":["fundamental_analysis","technical_analysis","sentiment_analysis","macro_analysis","contrarian_analysis"],"is_fast_track":true}',
            '{"ticker":"AAPL"}',
        ]
    )
    previous = _set_stub_llm(stub_llm)

    try:
        result = await goal_node({"user_query": "Run full 5Y analysis on AAPL"})
    finally:
        setattr(resources, "_llm_service", previous)

    assert result["plan_status"] == "approved"
    assert result["timeframe"] == "5y"
    assert result["timeframe_policy"]["ohlcv"]["period"] == "5y"
    assert "technical_analysis" in result["approved_agents"]
    assert result.get("final_output") is None


@pytest.mark.asyncio
async def test_goal_requests_clarification_for_ambiguous_timeframe(monkeypatch) -> None:
    _patch_resolver(monkeypatch, None)
    stub_llm = _StubLLMService(
        '{"response_mode":"direct_execution","assistant_response":"Executing now.","proposed_timeframe":"long term","proposed_agents":["fundamental_analysis"],"is_fast_track":true}'
    )
    previous = _set_stub_llm(stub_llm)

    try:
        result = await goal_node({"user_query": "Analyze Apple for the long term"})
    finally:
        setattr(resources, "_llm_service", previous)

    assert result["plan_status"] == "awaiting_clarification"
    assert result["timeframe"] is None
    assert result["timeframe_policy"] == {}


@pytest.mark.asyncio
async def test_goal_executes_when_user_answers_prior_clarification(monkeypatch) -> None:
    _patch_resolver(monkeypatch, "HDFCBANK")
    stub_llm = _StubLLMService(
        [
            '{"response_mode":"ask_plan_approval","assistant_response":"Proceeding with the 1-year full stock analysis for HDFC Bank as requested.","proposed_timeframe":"1y","proposed_agents":["fundamental_analysis","technical_analysis","sentiment_analysis","macro_analysis"],"is_fast_track":false}',
            '{"ticker":"HDFCBANK"}',
        ]
    )
    previous = _set_stub_llm(stub_llm)

    try:
        result = await goal_node(
            {
                "user_query": "Timeframe: 1 year Scope full stock analysis",
                "conversation_history": [
                    {"role": "user", "content": "Analyse the HDFC stock"},
                    {
                        "role": "assistant",
                        "content": "The query to analyze HDFC stock is broad. To refine the analysis, could you clarify the timeframe and scope?",
                    },
                ],
            }
        )
    finally:
        setattr(resources, "_llm_service", previous)

    assert result["plan_status"] == "approved"
    assert result["timeframe"] == "1y"
    assert result["goal"]["ticker"] == "HDFCBANK"
    assert result["goal"]["objective"] == "Analyse the HDFC stock"
    assert result.get("final_output") is None


@pytest.mark.asyncio
async def test_goal_node_audit_logs_timeframe_and_resolution(monkeypatch) -> None:
    _patch_resolver(monkeypatch, "HDFCBANK")
    stub_llm = _StubLLMService(
        [
            '{"response_mode":"direct_execution","assistant_response":"Proceeding with analysis.","proposed_timeframe":"1y","proposed_agents":["fundamental_analysis","technical_analysis"],"is_fast_track":true}',
            '{"ticker":"HDFCBANK","candidates":["HDFCBANK"]}',
        ]
    )
    previous = _set_stub_llm(stub_llm)

    try:
        result = await goal_node({"user_query": "Analyse HDFC Bank for 1 year"})
    finally:
        setattr(resources, "_llm_service", previous)

    audit = result["data"]["audit"]
    assert audit["node"] == "goal_node"
    assert audit["ticker"] == "HDFCBANK"
    assert audit["timeframe"] == "1y"
    assert audit["decision_summary"]["planner_mode"] == "direct_execution"
    assert audit["decision_summary"]["normalized_timeframe"] == "1y"
    assert audit["decision_summary"]["ticker_resolution"] == "resolved"
