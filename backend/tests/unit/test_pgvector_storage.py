from __future__ import annotations

from datetime import datetime, timedelta


def test_pgvector_storage_class_exists_and_has_required_methods():
    from storage.vector.pgvector_storage import PgVectorStorage

    storage = PgVectorStorage()
    for name in ("upsert_chunks", "chunk_and_upsert", "search", "get_news_info"):
        assert hasattr(storage, name), f"PgVectorStorage missing method: {name}"


def test_vector_client_exports_pgvector_storage():
    import storage.vector.client as vector_client

    assert hasattr(vector_client, "PgVectorStorage")
    assert vector_client.__all__ == ["PgVectorStorage"]


def test_chunk_and_upsert_uses_text_processor_and_calls_upsert(monkeypatch):
    from data.schemas.text import ProcessedChunk
    from storage.vector import pgvector_storage

    calls: dict[str, object] = {}

    class _StubProcessor:
        def __init__(self, use_embeddings: bool = False, **kwargs):
            calls["use_embeddings"] = use_embeddings

        def process_and_embed(self, text: str, metadata: dict):
            calls["text"] = text
            calls["metadata"] = metadata
            return [
                ProcessedChunk(
                    chunk_id="c1",
                    ticker=str(metadata["ticker"]),
                    text=text,
                    metadata={"published_date": "2026-01-01T00:00:00"},
                    embedding=[0.0] * 1024,
                )
            ]

    monkeypatch.setattr(pgvector_storage, "TextProcessor", _StubProcessor)

    storage = pgvector_storage.PgVectorStorage()
    captured = {}

    def _capture(chunks):
        captured["chunks"] = chunks

    monkeypatch.setattr(storage, "upsert_chunks", _capture)
    chunks = storage.chunk_and_upsert("hello", {"ticker": "ABC"})

    assert calls["use_embeddings"] is True
    assert captured["chunks"] == chunks
    assert len(chunks) == 1


def test_upsert_chunks_skips_invalid_embedding_dim_and_logs_warning(
    monkeypatch, caplog
):
    from data.schemas.text import ProcessedChunk
    from storage.vector.pgvector_storage import PgVectorStorage

    storage = PgVectorStorage()
    written = []

    def _fake_write(session, rows):
        written.extend(rows)

    monkeypatch.setattr(storage, "_upsert_chunk_rows", _fake_write)

    chunks = [
        ProcessedChunk(
            chunk_id="bad",
            ticker="ABC",
            text="bad",
            metadata={},
            embedding=[0.1, 0.2],
        ),
        ProcessedChunk(
            chunk_id="ok",
            ticker="ABC",
            text="ok",
            metadata={},
            embedding=[0.0] * 1024,
        ),
    ]

    storage.upsert_chunks(chunks)

    assert len(written) == 1
    assert written[0]["id"] == "ok"
    assert "Invalid embedding dim" in caplog.text


def test_search_fuses_vector_and_text_with_rrf_and_temporal_decay(monkeypatch):
    from storage.vector.pgvector_storage import PgVectorStorage
    from datetime import timezone

    storage = PgVectorStorage()
    now = datetime(2026, 1, 11, 0, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(storage, "_now", lambda: now)

    vector = [
        {
            "id": "a",
            "ticker": "ABC",
            "text": "v1",
            "metadata": {"published_date": (now - timedelta(days=10)).isoformat()},
            "embedding": [0.0] * 1024,
        }
    ]
    text = [
        {
            "id": "b",
            "ticker": "ABC",
            "text": "t1",
            "metadata": {"published_date": now.isoformat()},
            "embedding": [0.0] * 1024,
        }
    ]

    monkeypatch.setattr(storage, "_fetch_vector_candidates", lambda *a, **k: vector)
    monkeypatch.setattr(storage, "_fetch_text_candidates", lambda *a, **k: text)

    results = storage.search(
        query_embedding=[0.0] * 1024,
        query_text="anything",
        ticker="ABC",
        limit=5,
    )

    assert [r.chunk_id for r in results[:2]] == ["b", "a"]


def test_list_recent_by_tickers_returns_expected_results(monkeypatch):
    from storage.vector.pgvector_storage import PgVectorStorage
    from datetime import timezone

    storage = PgVectorStorage()
    now = datetime(2026, 1, 11, 0, 0, 0, tzinfo=timezone.utc)

    def _fake_exec(sql, params=None):
        class _FakeResult:
            def all(self):
                return [
                    ("chunk1", "ABC", "some text", {"source": "pgvector"}, now, [0.1]),
                    ("chunk2", "XYZ", "other text", {}, None, [0.2]),
                ]

        return _FakeResult()

    class _FakeSession:
        def __init__(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def exec(self, sql, params=None):
            assert "WHERE ticker IN" in str(sql) or "WHERE ticker = ANY" in str(sql)
            return _fake_exec(sql, params)

    monkeypatch.setattr(storage, "_session", _FakeSession)

    results = storage.list_recent_by_tickers(["ABC", "XYZ"], limit=5)
    assert len(results) == 2
    assert results[0].chunk_id == "chunk1"
    assert results[0].ticker == "ABC"
    assert results[0].text == "some text"
    assert results[0].metadata == {"source": "pgvector"}
    assert results[1].chunk_id == "chunk2"
    assert results[1].ticker == "XYZ"
