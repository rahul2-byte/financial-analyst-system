from __future__ import annotations

from typing import Any, cast

from app.services import embedding_service as embedding_module
from data.processors.text import TextProcessor


class _FakeModel:
    def encode(self, texts):
        if isinstance(texts, str):
            return _FakeVector([0.1, 0.2])
        return [_FakeVector([0.1, 0.2]) for _ in texts]


class _FakeVector(list):
    def tolist(self):
        return list(self)


class _FakeTimer:
    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self.started = False
        self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.callback()


def test_embedding_service_schedules_idle_unload(monkeypatch) -> None:
    timers: list[_FakeTimer] = []

    def _timer_factory(interval, callback):
        timer = _FakeTimer(interval, callback)
        timers.append(timer)
        return timer

    monkeypatch.setattr(
        embedding_module,
        "SentenceTransformer",
        lambda *_args, **_kwargs: _FakeModel(),
    )
    embedding_module.EmbeddingService._instance = None

    service = embedding_module.EmbeddingService(idle_ttl_seconds=300)
    service._timer_factory = cast(Any, _timer_factory)

    service.load_model()

    assert service.model is not None
    assert len(timers) == 1
    assert timers[0].interval == 300
    assert timers[0].started is True

    service.embed_text("hello world")

    assert len(timers) == 2
    assert timers[0].cancelled is True
    assert timers[1].started is True

    timers[1].fire()

    assert service.model is None


def test_text_processor_does_not_eagerly_unload_embedding_service(monkeypatch) -> None:
    class _StubEmbeddingService:
        def __init__(self):
            self.unload_calls = 0

        def embed_batch(self, texts):
            return [[0.25, 0.75] for _ in texts]

        def unload_model(self):
            self.unload_calls += 1

    stub = _StubEmbeddingService()
    monkeypatch.setattr("data.processors.text.EmbeddingService", lambda: stub)

    processor = TextProcessor(chunk_size=32, chunk_overlap=8, use_embeddings=True)
    chunks = processor.process_and_embed(
        "HDFC Bank expands branch network across India. " * 4,
        {"ticker": "HDFCBANK"},
    )

    assert chunks
    assert all(chunk.embedding == [0.25, 0.75] for chunk in chunks)
    assert stub.unload_calls == 0


def test_embedding_service_allows_zero_ttl_without_falling_back_to_default() -> None:
    embedding_module.EmbeddingService._instance = None

    service = embedding_module.EmbeddingService(idle_ttl_seconds=0)

    assert service.idle_ttl_seconds == 0
