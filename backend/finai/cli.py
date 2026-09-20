"""Parse CLI arguments and launch FIN-AI."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from app.observability.tracing import initialize_tracing

from .app import FinAIApp
from .plain import render_json, render_plain
from .session import FinAIRepl


def _validate_cli_paths(data_dir: Path, replay_path: Path | None) -> None:
    resolved = data_dir.expanduser().resolve()
    if resolved in {Path("/"), Path.home(), Path.cwd().resolve()}:
        raise ValueError("--data-dir must be a dedicated project data directory")
    if replay_path is not None:
        replay = replay_path.expanduser().resolve()
        if not replay.is_file():
            raise ValueError("--replay-snapshots must point to a file")
        if replay.stat().st_size > 256 * 1024:
            raise ValueError("--replay-snapshots is too large")


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI options without starting providers or touching the store."""
    parser = argparse.ArgumentParser(description="Interactive FIN-AI research terminal")
    parser.add_argument("--data-dir", type=Path, default=Path(".finai"))
    parser.add_argument("--session", default=None)
    parser.add_argument(
        "--replay-snapshots",
        type=Path,
        help="JSON mapping of provider operation to archived content hash; disables live providers",
    )
    parser.add_argument(
        "--plain", action="store_true", help="Print a readable one-shot response"
    )
    parser.add_argument(
        "--json", action="store_true", help="Print one-shot events as JSON"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write verbose diagnostics to .finai/logs/finai.log",
    )
    parser.add_argument(
        "--debug-payloads",
        action="store_true",
        help="Include bounded redacted payloads in diagnostics",
    )
    parser.add_argument(
        "--mode", choices=("guided", "review", "autonomous"), default="guided"
    )
    parser.add_argument("query", nargs="*", help="One-shot research query")
    return parser.parse_args(argv)


async def run_one_shot(repl: FinAIRepl, query: str, *, as_json: bool) -> None:
    """Stream one query and render it without starting the TUI."""
    try:
        events = [event async for event in repl.typed_stream(query)]
        output = render_json(events) if as_json else render_plain(events)
        sys.stdout.write(output)
    finally:
        await repl.hive_service.aclose()


async def run_plain_terminal(repl: FinAIRepl) -> None:
    """Run the line-oriented terminal when a TTY is unavailable."""
    try:
        await repl.run()
    finally:
        await repl.hive_service.aclose()


async def run_interactive(repl: FinAIRepl) -> None:
    """Start the Textual shell and connect it to the session stream."""
    app = FinAIApp(
        session_store=repl.store,
        compact_callback=repl.compact_context,
        mode=repl.mode,
    )

    def resume_session(session_id: str) -> None:
        repl.resume_session(session_id)
        app.session_store = repl.store

    def new_session() -> None:
        repl.new_session()
        app.session_store = repl.store

    app.session_callback = resume_session
    app.new_session_callback = new_session
    app.clear_pending_callback = repl.store.clear_pending

    async def stream(query: str):
        repl.mode = app.mode
        async for event in repl.typed_stream(query):
            yield event

    app.event_stream = stream
    try:
        await app.run_async()
    finally:
        await repl.hive_service.aclose()


def main() -> None:
    args = parse_arguments()
    try:
        tracing = initialize_tracing()
        if args.debug_payloads:
            os.environ["FINAI_DIAGNOSTICS"] = "payloads"
        elif args.debug:
            os.environ["FINAI_DIAGNOSTICS"] = "trace"
        log_dir = args.data_dir / "logs"
        _validate_cli_paths(args.data_dir, args.replay_snapshots)
        log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.DEBUG if args.debug else logging.WARNING,
            filename=log_dir / "finai.log",
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        replay_snapshots = (
            json.loads(args.replay_snapshots.read_text(encoding="utf-8"))
            if args.replay_snapshots
            else None
        )
        if replay_snapshots is not None and not isinstance(replay_snapshots, dict):
            raise ValueError("--replay-snapshots must contain a JSON object")
        repl = FinAIRepl(args.data_dir, args.session, replay_snapshots)
        repl.mode = args.mode
        if args.query:
            asyncio.run(run_one_shot(repl, " ".join(args.query), as_json=args.json))
            tracing.shutdown()
            return
        if sys.stdin.isatty() and sys.stdout.isatty():
            asyncio.run(run_interactive(repl))
        else:
            asyncio.run(run_plain_terminal(repl))
        tracing.shutdown()
    except KeyboardInterrupt:
        sys.exit(130)
