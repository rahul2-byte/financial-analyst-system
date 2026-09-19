import asyncio
from pathlib import Path

from app.core.resources import RuntimeResources
from finai.session import FinAIRepl


class _Model:
    def generate_stream(self, messages, model, **kwargs):
        del messages, model, kwargs

        async def stream():
            yield {"event": "token", "data": "Hello. What would you like to research?"}

        return stream()


class _InvalidReportModel:
    def generate_stream(self, messages, model, **kwargs):
        del messages, model, kwargs

        async def stream():
            yield {"event": "token", "data": "Unverified 900% return."}

        return stream()


def test_chat_response_and_run_artifact_are_visible(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "finai.session.build_runtime_resources",
        lambda **kwargs: RuntimeResources(llm_service=_Model(), yf_fetcher=object()),
    )
    repl = FinAIRepl(tmp_path, "test-session")

    async def collect():
        return [event async for event in repl.typed_stream("Hello")]

    events = asyncio.run(collect())
    completed = next(event for event in events if event.type == "run.completed")
    assert completed.terminal_status == "success"
    assert completed.artifact_path is not None
    assert Path(completed.artifact_path).exists()
    assert "Hello. What would you like to research?" in "".join(
        event.text for event in events if event.type == "response.delta"
    )


def test_old_tool_approval_does_not_block_a_new_query(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "finai.session.build_runtime_resources",
        lambda **kwargs: RuntimeResources(llm_service=_Model(), yf_fetcher=object()),
    )
    repl = FinAIRepl(tmp_path, "test-session")
    repl.store.write_pending({"kind": "approval", "query": "Old research"})

    async def collect():
        return [event async for event in repl.typed_stream("Hello")]

    events = asyncio.run(collect())
    assert events[-1].type == "run.completed"
    assert not any(event.type == "approval.requested" for event in events)
    assert repl.store.read_pending() is None


def test_invalid_report_gives_user_response_and_artifact(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "finai.session.build_runtime_resources",
        lambda **kwargs: RuntimeResources(
            llm_service=_InvalidReportModel(), yf_fetcher=object()
        ),
    )
    repl = FinAIRepl(tmp_path, "report-session")

    async def collect():
        return [event async for event in repl.typed_stream("Write a report on ABC.NS")]

    events = asyncio.run(collect())
    output = "".join(event.text for event in events if event.type == "response.delta")
    completed = next(event for event in events if event.type == "run.completed")
    assert "could not verify" in output.lower()
    assert "900%" not in output
    assert completed.terminal_status == "insufficient_data"
    assert completed.artifact_path is not None
    assert Path(completed.artifact_path).exists()


def test_line_terminal_prints_artifact_location(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(
        "finai.session.build_runtime_resources",
        lambda **kwargs: RuntimeResources(llm_service=_Model(), yf_fetcher=object()),
    )
    repl = FinAIRepl(tmp_path, "line-session")

    asyncio.run(repl.research("Hello"))

    output = capsys.readouterr().out
    assert "What would you like to research?" in output
    assert "Run artifact:" in output
