"""Render FIN-AI's terminal UI to SVG/PNG with a canned transcript.

No network or LLM: the app is fed the same typed events it receives from the
runtime. Run from the repository root:

    PYTHONPATH=backend uv run --offline python scripts/tui_screenshot.py
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend" / "tests")]

from app.events.models import (  # noqa: E402
    ClarificationRequested,
    EventFactory,
    ResearchEvent,
    RunCompleted,
    RunStarted,
)
from finai.app import Composer, FinAIApp  # noqa: E402
from finai.session_store import SessionStore  # noqa: E402
from fixtures.hdfc_run import (  # noqa: E402
    chat_only_events,
    hdfc_run_events,
    partial_run_events,
)

OUT = ROOT / "docs" / "design" / "screenshots"
FIRST = "Can you analyse HDFC Bank and tell me if I should buy it?"
SECOND = "HDFC Bank (HDFCBANK)"
CHAT = "Hello"
PARTIAL = "What do HDFC Bank's price, fundamentals and latest news say?"
CLARIFY = (
    "Several NSE/BSE instruments match HDFC. Reply with the exact symbol:\n"
    "- HDFCBANK (NSE) HDFC BANK LTD\n"
    "- HDFCLIFE (NSE) HDFC LIFE INSURANCE COMPANY LTD\n"
    "- HDFCAMC (NSE) HDFC ASSET MANAGEMENT COMPANY LTD"
)


async def _stream(query: str) -> AsyncIterator[ResearchEvent]:
    if query == CHAT:
        for event in chat_only_events():
            yield event
        return
    if query == PARTIAL:
        for event in partial_run_events():
            yield event
        return
    if query == FIRST:
        factory = EventFactory(uuid4())
        yield factory.make(RunStarted, query=query)
        yield factory.make(ClarificationRequested, prompt=CLARIFY)
        yield factory.make(RunCompleted, terminal_status="awaiting_clarification")
        return
    for event in hdfc_run_events():
        yield event


async def _send(app: FinAIApp, pilot, text: str) -> None:
    app.query_one("#composer", Composer).text = text
    await pilot.press("enter")
    await pilot.pause(0.6)


async def _shoot(
    name: str,
    size: tuple[int, int],
    *,
    prompts: tuple[str, ...] = (),
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = SessionStore(Path(tmp) / ".finai", "cf51ae036a06481991ebdefa87e829f6")
        app = FinAIApp(_stream, session_store=store)
        async with app.run_test(size=size) as pilot:
            for prompt in prompts:
                await _send(app, pilot, prompt)
            await pilot.pause(0.3)
            svg = app.save_screenshot(f"{name}.svg", path=str(OUT))
    png = OUT / f"{name}.png"
    if shutil.which("rsvg-convert"):
        # Fira Code lacks ⎿ and ✓; render the PNG with a mono font that has them.
        source = (
            Path(svg)
            .read_text(encoding="utf-8")
            .replace("Fira Code", "Adwaita Mono")
            .replace("<svg ", '<svg xml:space="preserve" ', 1)
        )
        tmp = OUT / f".{name}.render.svg"
        tmp.write_text(source, encoding="utf-8")
        try:
            subprocess.run(["rsvg-convert", "-o", str(png), str(tmp)], check=True)
        finally:
            tmp.unlink(missing_ok=True)
        print(f"wrote {png}")
    else:
        print(f"wrote {svg} (rsvg-convert not found; no PNG)")


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    full = (CHAT, FIRST, SECOND)
    await _shoot("transcript", (140, 42), prompts=full)
    await _shoot("empty", (140, 42))
    await _shoot("narrow", (90, 32), prompts=full)
    await _shoot("partial", (140, 42), prompts=(PARTIAL,))


if __name__ == "__main__":
    asyncio.run(main())
