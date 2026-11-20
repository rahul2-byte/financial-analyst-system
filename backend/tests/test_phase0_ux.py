"""Phase 0 regressions for plain/one-shot output."""

import asyncio
import contextlib
import io
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.events.models import (
    ClarificationRequested,
    EventFactory,
    SourcesUpdated,
)
from finai import cli
from finai.plain import render_plain


def _events(*items):
    factory = EventFactory(uuid4())
    return [factory.make(cls, **kw) for cls, kw in items]


def test_plain_lists_numbered_sources() -> None:
    sources = [
        {
            "title": "Annual Report",
            "source": "HDFC Bank",
            "url": "https://example.com/ar.pdf",
        }
    ]
    out = render_plain(_events((SourcesUpdated, {"sources": sources})))
    assert "[1] Annual Report — HDFC Bank" in out
    assert "https://example.com/ar.pdf" in out


def test_one_shot_clarification_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    async def typed_stream(_q: str):
        for event in _events((ClarificationRequested, {"prompt": "Which company?"})):
            yield event

    async def aclose() -> None:
        return None

    repl = SimpleNamespace(
        typed_stream=typed_stream,
        session_id="sess123",
        llm_service=SimpleNamespace(aclose=aclose),
    )
    code = asyncio.run(cli.run_one_shot(repl, "q", as_json=False))  # type: ignore[arg-type]
    out = capsys.readouterr().out
    assert code == 2
    assert "Which company?" in out
    assert "sess123" in out


# F-10 (cli part)
def test_tracing_init_noise_goes_to_stderr() -> None:
    out, err = io.StringIO(), io.StringIO()

    def noisy() -> None:
        print("Phoenix banner")

    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        cli.quiet_stdout(noisy)
    assert out.getvalue() == ""
    assert "Phoenix banner" in err.getvalue()
