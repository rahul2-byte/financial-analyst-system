import pytest
from unittest.mock import MagicMock, AsyncMock
from agents.financial.research.research_plan_node import research_plan_node
from data.schemas.text import ProcessedChunk
from app.core.node_resources import resources

class StubProcessedChunk:
    def __init__(self, text, metadata):
        self.text = text
        self.metadata = metadata

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
    # We also need to patch where EmbeddingService is instantiated if it is
    # But for now let's see how we'll use it in the node.
    
    # If the node uses EmbeddingService() we might need to patch the class
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
    assert "Chunk 2 text" in sentiment_params["text"]
    assert "Reuters" in sentiment_params["text"]
    assert "Bloomberg" in sentiment_params["text"]
    # It should NOT use the RSS news if RAG returned results
    assert "RSS Title" not in sentiment_params["text"]

    # Check contrarian_analysis parameters
    contrarian_params = tasks["contrarian_analysis"]["parameters"]
    # The requirement says: "Ensure task parameters now include the retrieved article text and source information."
    # For contrarian, it was: "sentiment_data": news_payload if isinstance(news_payload, list) else []
    # We should probably update this to include the RAG data.
    assert any("Chunk 1 text" in str(item) for item in contrarian_params["sentiment_data"])
    
@pytest.mark.asyncio
async def test_research_plan_fallbacks_to_rss_when_rag_empty(monkeypatch):
    # Mock Vector DB search returning empty
    mock_vector_db = MagicMock()
    mock_vector_db.search.return_value = []
    
    mock_embedding_service = MagicMock()
    mock_embedding_service.embed_text.return_value = [0.1] * 384
    
    import agents.financial.research.research_plan_node as node_module
    monkeypatch.setattr(node_module, "EmbeddingService", MagicMock(return_value=mock_embedding_service))

    state = {
        "user_query": "What is the sentiment for AAPL?",
        "goal": {"ticker": "AAPL", "instruments": [{"trading_symbol": "AAPL"}]},
        "approved_agents": ["sentiment_analysis"],
        "fetched_data": {
            "news": [{"title": "RSS Title", "summary": "RSS Summary"}]
        },
        "confidence_score": 0.7
    }

    result = await research_plan_node(state)
    
    tasks = {task["agent"]: task for task in result["tasks"]}
    sentiment_params = tasks["sentiment_analysis"]["parameters"]
    
    # Should fallback to RSS
    assert "RSS Title" in sentiment_params["text"]
    assert "RSS Summary" in sentiment_params["text"]
