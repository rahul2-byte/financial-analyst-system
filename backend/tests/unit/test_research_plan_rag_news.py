import pytest
from unittest.mock import MagicMock
from agents.financial.research.research_plan_node import research_plan_node
from data.schemas.text import ProcessedChunk
from app.core.node_resources import resources

@pytest.mark.asyncio
async def test_research_plan_uses_rag_for_sentiment_and_contrarian(monkeypatch):
    # Mock chunks returned by RAG
    mock_chunks = [
        ProcessedChunk(
            chunk_id="1",
            text="Chunk 1 text",
            ticker="AAPL",
            metadata={"source": "Reuters", "published_date": "2026-04-10"}
        ),
        ProcessedChunk(
            chunk_id="2",
            text="Chunk 2 text",
            ticker="AAPL",
            metadata={"source": "Bloomberg", "published_date": "2026-04-11"}
        )
    ]

    # Mock Vector DB search
    mock_vector_db = MagicMock()
    mock_vector_db.search.return_value = mock_chunks
    
    # Mock Embedding Service
    mock_embedding_service = MagicMock()
    mock_embedding_service.embed_text.return_value = [0.1] * 384
    
    # Patch resources
    monkeypatch.setattr(resources, "_vector_db", mock_vector_db)
    
    import agents.financial.research.research_plan_node as node_module
    monkeypatch.setattr(node_module, "EmbeddingService", MagicMock(return_value=mock_embedding_service))

    state = {
        "user_query": "What is the sentiment for AAPL?",
        "goal": {"ticker": "AAPL", "instruments": [{"trading_symbol": "AAPL"}]},
        "approved_agents": ["sentiment_analysis", "contrarian_analysis"],
        "fetched_data": {
            "news": [{"title": "RSS Title", "summary": "RSS Summary"}]
        },
        "confidence_score": 0.7
    }

    result = await research_plan_node(state)
    
    tasks = {task["agent"]: task for task in result["tasks"]}
    
    # Check sentiment_analysis parameters
    sentiment_params = tasks["sentiment_analysis"]["parameters"]
    assert "Chunk 1 text" in sentiment_params["text"]
    assert "Reuters" in sentiment_params["text"]
    # It should NOT use the RSS news
    assert "RSS Title" not in sentiment_params["text"]

    # Check contrarian_analysis parameters
    contrarian_params = tasks["contrarian_analysis"]["parameters"]
    assert any("Chunk 1 text" in str(item) for item in contrarian_params["sentiment_data"])
    assert not any("RSS Title" in str(item) for item in contrarian_params["sentiment_data"])

@pytest.mark.asyncio
async def test_research_plan_uses_placeholder_when_rag_empty(monkeypatch):
    # Mock Vector DB search returning empty
    mock_vector_db = MagicMock()
    mock_vector_db.search.return_value = []
    
    mock_embedding_service = MagicMock()
    mock_embedding_service.embed_text.return_value = [0.1] * 384
    
    # Patch resources
    monkeypatch.setattr(resources, "_vector_db", mock_vector_db)
    
    import agents.financial.research.research_plan_node as node_module
    monkeypatch.setattr(node_module, "EmbeddingService", MagicMock(return_value=mock_embedding_service))

    state = {
        "user_query": "What is the sentiment for AAPL?",
        "goal": {"ticker": "AAPL", "instruments": [{"trading_symbol": "AAPL"}]},
        "approved_agents": ["sentiment_analysis", "contrarian_analysis"],
        "fetched_data": {
            "news": [{"title": "RSS Title", "summary": "RSS Summary"}]
        },
        "confidence_score": 0.7
    }

    result = await research_plan_node(state)
    
    tasks = {task["agent"]: task for task in result["tasks"]}
    
    # Should use placeholder for sentiment_analysis
    sentiment_params = tasks["sentiment_analysis"]["parameters"]
    assert "Insufficient qualitative evidence found for research analysis" in sentiment_params["text"]
    assert "RSS Title" not in sentiment_params["text"]

    # Should use placeholder for contrarian_analysis
    contrarian_params = tasks["contrarian_analysis"]["parameters"]
    assert len(contrarian_params["sentiment_data"]) == 1
    placeholder = contrarian_params["sentiment_data"][0]
    assert placeholder["title"] == "Insufficient Data"
    assert "Insufficient qualitative evidence found for research analysis" in placeholder["summary"]
    assert placeholder["source"] == "None"
