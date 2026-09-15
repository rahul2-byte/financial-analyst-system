from datetime import UTC
from uuid import UUID, uuid4

import pytest
from app.events.models import (
    EventFactory,
    ProviderAttemptStarted,
    ProviderRetrying,
    RunCompleted,
    RunStarted,
    TextDelta,
)


def test_event_factory_assigns_shared_run_identity_and_sequence() -> None:
    factory = EventFactory(conversation_id=uuid4())

    started = factory.make(RunStarted, query="Analyze INFY")
    delta = factory.make(TextDelta, text="Evidence")
    completed = factory.make(RunCompleted, terminal_status="success", duration_ms=12.5)

    assert started.meta.run_id == delta.meta.run_id == completed.meta.run_id
    assert [started.meta.sequence, delta.meta.sequence, completed.meta.sequence] == [1, 2, 3]
    assert isinstance(UUID(str(started.meta.event_id)), UUID)
    assert started.meta.occurred_at.tzinfo == UTC


def test_event_models_reject_missing_required_payload() -> None:
    with pytest.raises(ValueError):
        TextDelta.model_validate({"type": "response.delta"})


def test_provider_events_share_the_run_trace_contract() -> None:
    factory = EventFactory(conversation_id=uuid4())

    attempt = factory.make(ProviderAttemptStarted, attempt=1)
    retry = factory.make(
        ProviderRetrying, attempt=1, status_code=504, delay_ms=250, reason="gateway"
    )

    assert attempt.type == "provider.attempt.started"
    assert retry.status_code == 504
    assert [attempt.meta.sequence, retry.meta.sequence] == [1, 2]
