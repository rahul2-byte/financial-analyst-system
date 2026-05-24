from unittest.mock import MagicMock

import pytest

from agents.financial.research.research_context_node import research_context_node
from agents.financial.research.research_plan_node import research_plan_node
from app.core.node_resources import resources
from data.schemas.text import ProcessedChunk


@pytest.mark.asyncio
async def test_research_context_node_uses_agent_specific_retrieval_queries(monkeypatch):
    captured_queries: list[str] = []
    mock_chunks = [
        ProcessedChunk(
            chunk_id="1",
            text="Management warned on margins",
            ticker="AAPL",
            metadata={"source": "Reuters", "published_date": "2026-04-10"},
        )
    ]

    def _search(**kwargs):
        captured_queries.append(kwargs["query_text"])
        return mock_chunks

    mock_vector_db = MagicMock()
    mock_vector_db.search.side_effect = _search
    monkeypatch.setattr(resources, "_vector_db", mock_vector_db)

    import agents.financial.research.context_assembly as assembly_module

    mock_embedding_service = MagicMock()
    mock_embedding_service.embed_text.return_value = [0.1] * 384
    monkeypatch.setattr(
        assembly_module,
        "EmbeddingService",
        MagicMock(return_value=mock_embedding_service),
    )

    plan = await research_plan_node(
        {
            "user_query": "Assess earnings risk for AAPL",
            "goal": {"ticker": "AAPL", "instruments": [{"trading_symbol": "AAPL"}]},
            "approved_agents": ["sentiment_analysis", "contrarian_analysis"],
            "timeframe": "1y",
            "hypotheses": [
                {
                    "statement": "Earnings quality may weaken and narrative may deteriorate"
                }
            ],
            "data_status": {
                "news": {"available": True, "coverage": 1.0, "freshness": 1.0},
                "fundamentals": {"available": True, "coverage": 1.0, "freshness": 1.0},
                "ohlcv": {"available": True, "coverage": 1.0, "freshness": 1.0},
                "macro": {"available": True, "coverage": 1.0, "freshness": 1.0},
            },
        }
    )

    result = await research_context_node(
        {
            **plan,
            "fetched_data": {"news": []},
            "data_status": {
                "news": {"available": True, "coverage": 1.0, "freshness": 1.0},
                "fundamentals": {"available": True, "coverage": 1.0, "freshness": 1.0},
                "ohlcv": {"available": True, "coverage": 1.0, "freshness": 1.0},
                "macro": {"available": True, "coverage": 1.0, "freshness": 1.0},
            },
        }
    )

    assert result["status"] == "success"
    assert len(captured_queries) == 2
    assert captured_queries[0] != captured_queries[1]
    contexts = result["task_contexts"]
    sentiment = contexts["sentiment_analysis"]
    contrarian = contexts["contrarian_analysis"]
    assert sentiment["evidence_bundle"]["retrieval"]["returned_count"] == 1
    assert contrarian["evidence_bundle"]["retrieval"]["returned_count"] == 1
    evidence_item = sentiment["evidence_bundle"]["qualitative_inputs"][0]
    assert evidence_item["evidence_id"] == "1"
    assert evidence_item["metadata"]["evidence_id"] == "1"
    assert result["citation_index"]["1"]["source"] == "Reuters"
    assert result["citation_index"]["1"]["published_date"] == "2026-04-10"


@pytest.mark.asyncio
async def test_research_context_node_uses_explicit_news_fallback_when_retrieval_is_empty(
    monkeypatch,
):
    mock_vector_db = MagicMock()
    mock_vector_db.search.return_value = []
    monkeypatch.setattr(resources, "_vector_db", mock_vector_db)

    import agents.financial.research.context_assembly as assembly_module

    mock_embedding_service = MagicMock()
    mock_embedding_service.embed_text.return_value = [0.1] * 384
    monkeypatch.setattr(
        assembly_module,
        "EmbeddingService",
        MagicMock(return_value=mock_embedding_service),
    )

    plan = await research_plan_node(
        {
            "user_query": "Assess earnings risk for AAPL",
            "goal": {"ticker": "AAPL", "instruments": [{"trading_symbol": "AAPL"}]},
            "approved_agents": ["sentiment_analysis"],
            "timeframe": "1y",
        }
    )

    result = await research_context_node(
        {
            **plan,
            "fetched_data": {
                "news": [{"title": "RSS Title", "summary": "RSS Summary"}]
            },
            "data_status": {
                "news": {"available": True, "coverage": 1.0, "freshness": 1.0}
            },
        }
    )

    context = result["task_contexts"]["sentiment_analysis"]
    assert result["status"] == "success"
    assert (
        context["evidence_bundle"]["retrieval"]["failure_reason"] == "retrieval_empty"
    )
    assert context["evidence_bundle"]["retrieval"]["retrieval_source"] == "vector_db"
    assert context["evidence_bundle"]["warnings"] == ["used_fetched_news_fallback"]
    evidence_item = context["evidence_bundle"]["qualitative_inputs"][0]
    assert "RSS Title" in evidence_item["text"]
    assert evidence_item["evidence_id"]
    assert evidence_item["metadata"]["evidence_id"] == evidence_item["evidence_id"]
    assert result["citation_index"][evidence_item["evidence_id"]]["source"] == "Fetched news"


@pytest.mark.asyncio
async def test_research_context_audit_logs_retrieval_and_dimensions(
    monkeypatch,
) -> None:
    mock_vector_db = MagicMock()
    mock_vector_db.search.return_value = []
    monkeypatch.setattr(resources, "_vector_db", mock_vector_db)

    import agents.financial.research.context_assembly as assembly_module

    mock_embedding_service = MagicMock()
    mock_embedding_service.embed_text.return_value = [0.1] * 384
    monkeypatch.setattr(
        assembly_module,
        "EmbeddingService",
        MagicMock(return_value=mock_embedding_service),
    )

    plan = await research_plan_node(
        {
            "user_query": "Assess earnings risk for AAPL",
            "goal": {"ticker": "AAPL", "instruments": [{"trading_symbol": "AAPL"}]},
            "approved_agents": ["sentiment_analysis"],
            "timeframe": "1y",
            "hypotheses": [{"statement": "H1"}],
        }
    )

    result = await research_context_node(
        {
            **plan,
            "goal": {"ticker": "AAPL", "instruments": [{"trading_symbol": "AAPL"}]},
            "fetched_data": {
                "news": [{"title": "RSS Title", "summary": "RSS Summary"}]
            },
            "data_status": {
                "news": {"available": True, "coverage": 1.0, "freshness": 1.0}
            },
        }
    )

    audit = result["data"]["audit"]
    assert audit["node"] == "research_context_node"
    assert audit["ticker"] == "AAPL"

    summary = audit["decision_summary"]
    assert summary["agents_configured"] == ["sentiment_analysis"]

    sentiment_diag = summary["retrieval_diagnostics"]["sentiment_analysis"]
    assert sentiment_diag["returned_count"] == 0
    assert sentiment_diag["failure_reason"] == "retrieval_empty"
    assert sentiment_diag["fallback_used"] is True
