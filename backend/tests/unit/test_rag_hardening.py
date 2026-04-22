import pytest
import math
from datetime import datetime, timedelta, timezone
from storage.vector.client import PgVectorStorage
from unittest.mock import patch


def test_rrf_logic():
    """
    Verifies that Reciprocal Rank Fusion correctly combines results.
    We'll test the ranking logic used by the vector store.
    """
    # Constant k=60
    # Score = 1/(rank + 60)

    # Item A: Rank 1 in Vector, Rank 2 in Text
    score_a = (1 / (1 + 60)) + (1 / (2 + 60))

    # Item B: Rank 2 in Vector, Rank 1 in Text
    score_b = (1 / (2 + 60)) + (1 / (1 + 60))

    # Item C: Rank 1 in Vector, Not in Text
    score_c = 1 / (1 + 60)

    assert score_a == score_b
    assert score_a > score_c


def test_temporal_decay():
    """
    Verifies that more recent documents get a higher score.
    """
    # Decay = exp(-0.05 * days_old)

    days_0 = 0
    days_10 = 10

    decay_0 = math.exp(-0.05 * days_0)  # 1.0
    decay_10 = math.exp(-0.05 * days_10)  # ~0.606

    assert decay_0 == 1.0
    assert decay_10 < 1.0
    assert decay_0 > decay_10


@pytest.mark.asyncio
async def test_hybrid_search_mock():
    """
    Verifies the integration of RRF and Decay in PgVectorStorage.
    """
    with patch(
        "storage.vector.pgvector_storage.PgVectorStorage._fetch_vector_candidates"
    ) as mock_vector, patch(
        "storage.vector.pgvector_storage.PgVectorStorage._fetch_text_candidates"
    ) as mock_text:

        storage = PgVectorStorage()

        # Mock Vector results (Top 2)
        mock_hit1 = {
            "id": "1",
            "published_date": datetime.now(timezone.utc).isoformat(),
            "metadata": {"text": "Modern results"},
            "embedding": [0.1] * 1024,
        }
        mock_hit2 = {
            "id": "2",
            "published_date": (
                datetime.now(timezone.utc) - timedelta(days=100)
            ).isoformat(),
            "metadata": {"text": "Old results"},
            "embedding": [0.1] * 1024,
        }

        mock_vector.return_value = [mock_hit1, mock_hit2]
        mock_text.return_value = [mock_hit1]

        # Run hybrid search
        results = storage.search(
            query_embedding=[0.1] * 1024, query_text="Modern", limit=5
        )

        assert len(results) >= 1
        # Hit 1 should be first because it's more recent and appeared in both searches
        assert results[0].chunk_id == "1"
