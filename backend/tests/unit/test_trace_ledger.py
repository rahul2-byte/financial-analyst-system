import json
from pathlib import Path
from uuid import uuid4

from app.events.ledger import TraceLedger
from app.events.models import EventFactory, RunStarted


def _event(query: str = "Analyze INFY") -> RunStarted:
    return EventFactory(uuid4()).make(RunStarted, query=query)


def test_ledger_appends_events_with_contiguous_sequences(tmp_path: Path) -> None:
    ledger = TraceLedger(tmp_path / "session")
    first = _event()
    second = _event()

    ledger.append(first)
    ledger.append(second)

    records = ledger.read()
    assert [record["sequence"] for record in records] == [1, 2]
    assert records[0]["event_type"] == "run.started"
    assert records[0]["payload"]["query"] == "Analyze INFY"


def test_ledger_redacts_secrets_before_persisting(tmp_path: Path) -> None:
    ledger = TraceLedger(tmp_path / "session")
    event = _event("Authorization: Bearer super-secret-token")

    ledger.append(event)

    raw = ledger.path.read_text(encoding="utf-8")
    assert "super-secret-token" not in raw
    assert "[REDACTED]" in raw


def test_ledger_spills_large_payload_to_hashed_artifact(tmp_path: Path) -> None:
    ledger = TraceLedger(tmp_path / "session", inline_limit=20)
    event = _event("x" * 100)

    ledger.append(event)

    record = ledger.read()[0]
    assert record["artifact_refs"]
    artifact = ledger.session_dir / record["artifact_refs"][0]["path"]
    assert artifact.exists()
    assert json.loads(artifact.read_text(encoding="utf-8"))["query"] == "x" * 100


def test_ledger_assigns_monotonic_sequences_independent_of_source(tmp_path: Path) -> None:
    ledger = TraceLedger(tmp_path / "session")
    first = _event()
    ledger.append(first)
    ledger.append(first)

    assert [record["sequence"] for record in ledger.read()] == [1, 2]


def test_ledger_ignores_a_torn_final_record(tmp_path: Path) -> None:
    ledger = TraceLedger(tmp_path / "session")
    ledger.append(_event())
    with ledger.path.open("a", encoding="utf-8") as handle:
        handle.write('{"schema_version": 1')

    recovered = TraceLedger(tmp_path / "session")
    recovered.append(_event("after recovery"))

    assert [record["sequence"] for record in recovered.read()] == [1, 2]


def test_ledger_can_batch_noncritical_stream_events(
    tmp_path: Path, monkeypatch
) -> None:
    ledger = TraceLedger(tmp_path / "session")
    syncs: list[int] = []
    monkeypatch.setattr("app.events.ledger.os.fsync", lambda fd: syncs.append(fd))

    ledger.append(_event(), durable=False)

    assert syncs == []
