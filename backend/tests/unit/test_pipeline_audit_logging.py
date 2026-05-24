from __future__ import annotations

import pytest

import agents.financial.data.data_check_node as data_check_module
import agents.financial.data.data_fetch_node as data_fetch_module
from agents.financial.data.data_plan_node import data_plan_node
from agents.financial.data.data_check_node import data_check_node
from agents.financial.data.data_fetch_node import data_fetch_node
from agents.orchestration.router_node import router_node
from app.core.node_resources import resources
from app.core.orchestration_schemas import OfflineStatus


@pytest.mark.asyncio
async def test_router_audit_entry_contains_decision_reason() -> None:
    state = {
        "goal": {"ticker": "HDFCBANK"},
        "iteration_count": 1,
        "data_status": {},
        "tasks": [],
    }

    result = await router_node(state)

    assert result["status"] == "success"
    audit = result["data"]["audit"]
    assert audit["node"] == "router_node"
    assert audit["ticker"] == "HDFCBANK"
    assert audit["decision_summary"]["router_decision"] == result["router_decision"]
    assert audit["decision_summary"]["iteration"] == result["iteration_count"]
    assert "decision_reason_hint" in audit["decision_summary"]
    assert "retry_count_by_domain" in audit["decision_summary"]


@pytest.mark.asyncio
async def test_data_check_audit_logs_resolution_and_missing_datasets(
    monkeypatch,
) -> None:
    async def _stub_audit(ticker: str):
        return (
            OfflineStatus(
                data_available=False,
                ticker_used="AAPL",
                reasoning="Resolved locally but news is missing.",
                ohlcv_data={"has_data": True, "latest_date": "2026-04-10T00:00:00"},
                fundamentals_data={
                    "has_data": True,
                    "latest_date": "2026-04-09T00:00:00",
                },
                news_data={"has_data": False},
                macro_data={"has_data": True, "latest_date": "2026-04-10T00:00:00"},
            ),
            [],
        )

    monkeypatch.setattr(data_check_module, "_run_local_offline_audit", _stub_audit)

    result = await data_check_node(
        {
            "goal": {"ticker": "APPLE"},
            "data_status": {},
            "timeframe_policy": {"news": {"minimum_coverage_ratio": 0.5}},
        }
    )

    audit = result["data"]["audit"]
    assert audit["node"] == "data_check_node"
    assert audit["ticker"] == "AAPL"
    assert audit["decision_summary"]["missing_datasets"] == ["news"]
    assert audit["decision_summary"]["resolved_ticker"] == "AAPL"
    assert audit["decision_summary"]["next_action"] == "run_data_plan"


@pytest.mark.asyncio
async def test_data_plan_audit_logs_prioritized_operations() -> None:
    result = await data_plan_node(
        {
            "goal": {"ticker": "AAPL"},
            "data_check": {
                "missing_datasets": ["news"],
                "stale_datasets": ["fundamentals"],
            },
            "timeframe_policy": {
                "news": {"minimum_items": 10},
                "fundamentals": {"required_fields": ["marketCap"]},
            },
        }
    )

    audit = result["data"]["audit"]
    assert audit["node"] == "data_plan_node"
    assert audit["ticker"] == "AAPL"
    assert audit["decision_summary"]["plan_count"] == 2
    assert audit["decision_summary"]["missing_datasets"] == ["news"]
    assert audit["decision_summary"]["stale_datasets"] == ["fundamentals"]
    assert audit["decision_summary"]["symbols"] == ["AAPL"]
    assert audit["decision_summary"]["next_action"] == "run_data_fetch"
    assert audit["decision_summary"]["planned_operations"] == [
        {"dataset": "news", "action": "materialize", "priority": "P0"},
        {"dataset": "fundamentals", "action": "refresh", "priority": "P1"},
    ]


class _AuditStubYFinanceFetcher:
    def fetch_stock_price(self, ticker: str, period: str = "1mo", interval: str = "1d"):
        return []

    def fetch_company_fundamentals(self, ticker: str):
        return {"marketCap": 1}

    def fetch_macro_indicators(self):
        return {"NIFTY_50": 22000}


class _EmptyNewsRunner:
    async def run(self, company, time_window_days):
        return []


@pytest.mark.asyncio
async def test_data_fetch_audit_logs_dataset_outcomes(monkeypatch) -> None:
    previous_yf = resources._yf_fetcher
    previous_sql = resources._sql_db
    previous_vector = resources._vector_db
    monkeypatch.setattr(resources, "_yf_fetcher", _AuditStubYFinanceFetcher())
    monkeypatch.setattr(
        data_fetch_module, "_build_news_pipeline_runner", lambda: _EmptyNewsRunner()
    )

    class _SqlStub:
        def save_ohlcv(self, rows):
            return None

        def upsert_fundamentals(self, payload):
            return None

        def update_cache_index(self, *args, **kwargs):
            return None

        def save_fundamentals(self, ticker, payload):
            return None

        def save_news_articles(self, articles):
            return None

        def save_news_article_chunks(self, chunks):
            return None

        def get_news_cache_info(self, ticker):
            return {"has_data": False}

    class _VectorStub:
        def upsert_news_chunks(self, chunks):
            return None

        def get_news_info(self, ticker):
            return {"has_news": False}

    monkeypatch.setattr(resources, "_sql_db", _SqlStub())
    monkeypatch.setattr(resources, "_vector_db", _VectorStub())

    try:
        result = await data_fetch_node(
            {
                "goal": {"ticker": "AAPL"},
                "user_query": "Analyze AAPL",
                "data_status": {},
                "data_plan": [
                    {"dataset": "news", "priority": "P0", "action": "fetch"},
                    {
                        "dataset": "fundamentals",
                        "priority": "P1",
                        "action": "fetch",
                    },
                ],
                "retry_count_by_domain": {},
            }
        )
    finally:
        setattr(resources, "_yf_fetcher", previous_yf)
        setattr(resources, "_sql_db", previous_sql)
        setattr(resources, "_vector_db", previous_vector)

    audit = result["data"]["audit"]
    assert audit["node"] == "data_fetch_node"
    assert audit["ticker"] == "AAPL"
    assert audit["decision_summary"]["planned_datasets"] == ["news", "fundamentals"]
    assert audit["decision_summary"]["fetched_dataset_count"] == 2
    assert "dataset_outcomes_detailed" in audit["decision_summary"]
    assert "retry_count_by_domain" in audit["decision_summary"]
    assert audit["decision_summary"]["dataset_outcomes"] == [
        {"dataset": "news", "available": False, "error": "INSUFFICIENT_DATA"},
        {"dataset": "fundamentals", "available": True, "error": None},
    ]


@pytest.mark.asyncio
async def test_data_fetch_audit_only_reports_datasets_touched_by_current_plan(
    monkeypatch,
) -> None:
    previous_yf = resources._yf_fetcher
    previous_sql = resources._sql_db
    previous_vector = resources._vector_db
    monkeypatch.setattr(resources, "_yf_fetcher", _AuditStubYFinanceFetcher())
    monkeypatch.setattr(
        data_fetch_module, "_build_news_pipeline_runner", lambda: _EmptyNewsRunner()
    )

    class _SqlStub:
        def save_ohlcv(self, rows):
            return None

        def upsert_fundamentals(self, payload):
            return None

        def update_cache_index(self, *args, **kwargs):
            return None

        def save_fundamentals(self, ticker, payload):
            return None

        def save_news_articles(self, articles):
            return None

        def save_news_article_chunks(self, chunks):
            return None

        def get_news_cache_info(self, ticker):
            return {"has_data": False}

    class _VectorStub:
        def upsert_news_chunks(self, chunks):
            return None

        def get_news_info(self, ticker):
            return {"has_news": False}

    monkeypatch.setattr(resources, "_sql_db", _SqlStub())
    monkeypatch.setattr(resources, "_vector_db", _VectorStub())

    try:
        result = await data_fetch_node(
            {
                "goal": {"ticker": "AAPL"},
                "user_query": "Analyze AAPL",
                "data_status": {
                    "macro": {
                        "available": True,
                        "coverage": 1.0,
                        "freshness": 1.0,
                        "error": None,
                    }
                },
                "data_plan": [
                    {
                        "dataset": "fundamentals",
                        "priority": "P1",
                        "action": "fetch",
                    }
                ],
                "retry_count_by_domain": {},
            }
        )
    finally:
        setattr(resources, "_yf_fetcher", previous_yf)
        setattr(resources, "_sql_db", previous_sql)
        setattr(resources, "_vector_db", previous_vector)

    audit = result["data"]["audit"]
    assert audit["decision_summary"]["planned_datasets"] == ["fundamentals"]
    assert audit["decision_summary"]["fetched_dataset_count"] == 1
    assert audit["decision_summary"]["dataset_outcomes"] == [
        {"dataset": "fundamentals", "available": True, "error": None}
    ]


@pytest.mark.asyncio
async def test_synthesis_audit_logs_decisions_and_evidence() -> None:
    from agents.quality.synthesis_node import synthesis_node

    state = {
        "goal": {"ticker": "AAPL"},
        "results": {
            "agent_a": {
                "claims": [{"claim_id": "c1", "importance": "major", "text": "Claim 1"}]
            },
            "agent_b": {
                "claims": [{"claim_id": "c2", "importance": "minor", "text": "Claim 2"}]
            },
        },
        "tool_registry": [],
        "claim_verification": {"verified_claim_ids": ["c1"]},
        "evidence_strength": 0.85,
    }

    result = await synthesis_node(state)

    audit = result["data"]["audit"]
    assert audit["node"] == "synthesis_node"
    assert audit["ticker"] == "AAPL"

    summary = audit["decision_summary"]
    assert summary["available_agents"] == ["agent_a", "agent_b"]
    assert summary["verified_claim_count"] == 1
    assert summary["major_claim_count"] == 1
    assert summary["evidence_strength"] == 0.85
    assert summary["decision"] == "watchlist"
    assert "insufficiency_markers_count" in summary
    assert "reasoning" in summary


@pytest.mark.asyncio
async def test_quality_nodes_emit_decision_rationale_in_audit() -> None:
    from agents.quality.critic_node import critic_node

    state = {
        "goal": {"ticker": "MSFT"},
        "results": {
            "synthesis": {
                "claims": [
                    {"claim_id": "c1", "importance": "major", "text": "c1 text"},
                    {"claim_id": "c2", "importance": "major", "text": "c2 text"},
                ]
            }
        },
        "citation_index": {},
        "evidence_strength": 0.9,
        "tasks": [{"task_id": "t1", "priority": "P2"}],
    }

    # We will mock verify_claims and arbitrate_conflicts to control their output,
    # or just let them run if they don't hit external services.
    # verify_claims might return invalid_major_claim_ids if no citations.
    result = await critic_node(state)

    audit = result["data"]["audit"]
    assert audit["node"] == "critic_node"
    assert audit["ticker"] == "MSFT"

    summary = audit["decision_summary"]
    assert summary["critic_decision"] in {"approve", "retry", "conflict"}
    assert "verified_claim_count" in summary
    assert "invalid_major_claim_ids" in summary
    assert "conflict_resolved" in summary
    assert "force_replan" in summary


@pytest.mark.asyncio
async def test_validation_audit_logs_gate_and_final_decision() -> None:
    from agents.orchestration.validation_node import validation_node

    state = {
        "goal": {"ticker": "TSLA"},
        "results": {"synthesis": {"decision": "bullish"}},
        "required_agents": [],
        "approved_agents": [],
        "claim_verification": {"verified_claim_ids": []},
        "conflict_record": {"unresolved_claim_pairs": []},
        "evidence_strength": 0.9,
        "coverage_report": {"source_diversity_score": 0.8},
        "confidence_score": 0.75,
    }

    result = await validation_node(state)

    audit = result["data"]["audit"]
    assert audit["node"] == "validation_node"
    assert audit["ticker"] == "TSLA"

    summary = audit["decision_summary"]
    assert "gate_result" in summary
    assert "hard_stop_reason" in summary
    assert summary["final_decision"] == "bullish"
    assert summary["final_confidence"] == 0.75


@pytest.mark.asyncio
async def test_evaluator_audit_logs_intelligence_decisions(monkeypatch) -> None:
    from agents.quality.evaluator_node import evaluator_node

    state = {
        "goal": {"ticker": "NVDA"},
        "final_output": {"decision": "bullish", "confidence_score": 0.9},
        "retry_count_by_domain": {"research": 0},
        "user_query": "analyze nvda",
    }

    # Mock LLM response to avoid actual calls
    class _MockResponse:
        content = '{"score": 0.85, "error_type": "none", "feedback": "good"}'

    async def mock_generate_message(*args, **kwargs):
        return _MockResponse()

    from app.core.node_resources import resources

    monkeypatch.setattr(
        resources.llm_service, "generate_message", mock_generate_message
    )

    class _MockSqlDB:
        def get_recent_interactions(self, limit=20):
            return []

        def log_interaction(self, **kwargs):
            pass

        def log_error(self, **kwargs):
            pass

        def record_performance_metric(self, **kwargs):
            pass

    monkeypatch.setattr(resources, "_sql_db", _MockSqlDB())

    result = await evaluator_node(state)

    audit = result["data"]["audit"]
    assert audit["node"] == "evaluator_node"
    assert audit["ticker"] == "NVDA"

    summary = audit["decision_summary"]
    assert summary["evaluator_score"] == 0.85
    assert summary["evaluator_error_type"] == "none"
    assert summary["intelligence_decision"] == "TERMINATE_SUCCESS"
    assert summary["retry_count"] == 0


@pytest.mark.asyncio
async def test_conflict_resolution_node_emits_audit_summary() -> None:
    from agents.quality.conflict_resolution_node import conflict_resolution_node

    state = {
        "goal": {"ticker": "RELIANCE"},
        "results": {
            "synthesis": {
                "decision": "watchlist",
                "risks": ["existing risk"],
            }
        },
        "confidence_score": 0.66,
    }

    result = await conflict_resolution_node(state)

    audit = result["data"]["audit"]
    assert audit["node"] == "conflict_resolution_node"
    assert audit["ticker"] == "RELIANCE"
    summary = audit["decision_summary"]
    assert summary["resolution_method"] == "recency_and_evidence_weighting"
    assert summary["next_action"] == "run_synthesis"
    assert summary["resolved"] is True


@pytest.mark.asyncio
async def test_validation_missing_synthesis_emits_failure_audit() -> None:
    from agents.orchestration.validation_node import validation_node

    result = await validation_node({"goal": {"ticker": "SBIN"}})

    assert result["status"] == "failure"
    audit = result["data"]["audit"]
    assert audit["node"] == "validation_node"
    assert audit["ticker"] == "SBIN"
    summary = audit["decision_summary"]
    assert summary["gate_result"] == "hard_stop"
    assert summary["hard_stop_reason"] == "missing_synthesis"


@pytest.mark.asyncio
async def test_validation_missing_evidence_emits_failure_audit() -> None:
    from agents.orchestration.validation_node import validation_node

    state = {
        "goal": {"ticker": "ICICIBANK"},
        "results": {
            "synthesis": {
                "claims": [{"claim_id": "c-1", "importance": "major"}],
            }
        },
    }

    result = await validation_node(state)

    assert result["status"] == "failure"
    audit = result["data"]["audit"]
    assert audit["node"] == "validation_node"
    assert audit["ticker"] == "ICICIBANK"
    summary = audit["decision_summary"]
    assert summary["gate_result"] == "hard_stop"
    assert summary["hard_stop_reason"] == "missing_claim_evidence"
