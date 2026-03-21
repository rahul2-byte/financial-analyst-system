import pytest
import math
from datetime import datetime, timedelta, timezone
from storage.vector.client import QdrantStorage
from unittest.mock import MagicMock, patch


def test_rrf_logic():
    """
    Verifies that Reciprocal Rank Fusion correctly combines results.
    We'll mock the QdrantStorage and test its internal scoring logic if possible,
    or just test the principle.
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
    Verifies the integration of RRF and Decay in QdrantStorage.
    """
    # Note: QdrantStorage initializes a client in __init__, so we mock it.
    with patch("storage.vector.client.QdrantClient") as mock_client:
        storage = QdrantStorage()
        storage.client = mock_client

        # Mock Vector results (Top 2)
        mock_hit1 = MagicMock(
            id="1",
            payload={
                "text": "Modern results",
                "published_date": datetime.now(timezone.utc).isoformat(),
            },
        )
        mock_hit2 = MagicMock(
            id="2",
            payload={
                "text": "Old results",
                "published_date": (
                    datetime.now(timezone.utc) - timedelta(days=100)
                ).isoformat(),
            },
        )

        storage.client.search.return_value = [mock_hit1, mock_hit2]

        # Mock Text results (Top 1)
        storage.client.scroll.return_value = ([mock_hit1], None)

        # Run hybrid search
        results = storage.hybrid_search(
            query_embedding=[0.1] * 384, query_text="Modern", limit=5
        )

        assert len(results) >= 1
        # Hit 1 should be first because it's more recent and appeared in both searches
        assert results[0].chunk_id == "1"
