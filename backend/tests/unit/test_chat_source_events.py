from uuid import uuid4

from app.events.models import EventFactory, RunCompleted, SourcesUpdated
from app.routes.chat import _to_sse_event


def test_chat_stream_exposes_sources_and_run_identity() -> None:
    factory = EventFactory(uuid4())
    sources = factory.make(
        SourcesUpdated,
        sources=[{"name": "Exchange filing", "url": "https://example.test/filing"}],
    )
    completed = factory.make(RunCompleted, terminal_status="partial")

    source_event = _to_sse_event(sources)
    done_event = _to_sse_event(completed)

    assert source_event is not None
    assert source_event.data == {"sources": sources.sources}
    assert done_event is not None
    assert done_event.data == {
        "status": "partial",
        "run_id": str(completed.meta.run_id),
    }
