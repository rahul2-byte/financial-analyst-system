"""Parse CLI arguments and launch FIN-AI."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypeVar

from app.core.resources import MissingOpenRouterKeyError
from app.events.models import ResearchEvent
from app.observability.tracing import initialize_tracing

from .app import FinAIApp
from .plain import render_event
from .session import FinAIRepl

_T = TypeVar("_T")


def quiet_stdout(call: Callable[[], _T]) -> _T:
    """Run a call whose console output must not reach machine-readable stdout."""
    with contextlib.redirect_stdout(sys.stderr):
        return call()


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
    parser = argparse.ArgumentParser(
        description="Interactive FIN-AI research terminal",
        epilog=EXIT_CODE_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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
        "--json",
        action="store_true",
        help="Stream one-shot events as JSON lines (one object per event)",
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


EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CLARIFICATION = 2
EXIT_DEGRADED = 3
EXIT_INTERRUPTED = 130

EXIT_CODE_HELP = """exit codes (one-shot mode):
  0    run completed with sufficient evidence
  1    run failed, was denied or was cancelled
  2    clarification needed; re-run with --session <id> "<your answer>"
  3    completed with limited/partial/insufficient evidence or a validation
       fallback (terminal_status partial, insufficient_data,
       completed_with_limited_evidence, completed_with_limits, or
       evidence_status other than complete)
  130  interrupted with Ctrl+C

output streams (one-shot mode):
  stdout  response text as it streams (or one JSON event per line with --json)
  stderr  progress lines (stages, tool start/finish) and the run summary
"""

_DEGRADED_STATUSES = frozenset(
    {
        "partial",
        "insufficient_data",
        "completed_with_limited_evidence",
        "completed_with_limits",
    }
)
_FAILED_STATUSES = frozenset({"denied", "failed", "cancelled"})
_STDOUT_EVENTS = frozenset(
    {
        "response.delta",
        "sources.updated",
        "clarification.requested",
        "approval.requested",
    }
)
_STDERR_EVENTS = frozenset(
    {
        "stage.started",
        "tool.started",
        "tool.completed",
        "tool.failed",
        "provider.failed",
        "run.failed",
        "run.cancelled",
        "run.completed",
    }
)


def exit_code_for(events: Sequence[ResearchEvent]) -> int:
    """Map a finished run's terminal events to a process exit code."""
    failed = clarification = degraded = False
    for event in events:
        if event.type == "run.failed" or event.type == "run.cancelled":
            failed = True
        elif event.type == "clarification.requested":
            clarification = True
        elif event.type == "run.completed":
            status = event.terminal_status
            if status == "awaiting_clarification":
                clarification = True
            elif status in _FAILED_STATUSES:
                failed = True
            elif status in _DEGRADED_STATUSES or event.evidence_status not in {
                None,
                "complete",
            }:
                degraded = True
    if failed:
        return EXIT_FAILED
    if clarification:
        return EXIT_CLARIFICATION
    if degraded:
        return EXIT_DEGRADED
    return EXIT_OK


async def run_one_shot(repl: FinAIRepl, query: str, *, as_json: bool) -> int:
    """Stream one query, emitting each event as it arrives.

    Plain mode writes response text to stdout and progress to stderr; JSON mode
    writes one JSON object per event (JSONL) to stdout. See EXIT_CODE_HELP.
    """
    events: list[ResearchEvent] = []
    wrote_text = False
    try:
        async for event in repl.typed_stream(query):
            events.append(event)
            if as_json:
                sys.stdout.write(json.dumps(event.model_dump(mode="json")) + "\n")
                sys.stdout.flush()
                if event.type == "clarification.requested":
                    sys.stderr.write(
                        f"Needs clarification; session {repl.session_id}\n"
                    )
                continue
            text = render_event(event, repl.session_id)
            if not text:
                continue
            if event.type in _STDOUT_EVENTS:
                wrote_text = wrote_text or event.type == "response.delta"
                sys.stdout.write(text)
                sys.stdout.flush()
            elif event.type in _STDERR_EVENTS:
                sys.stderr.write(text)
                sys.stderr.flush()
        if wrote_text and not as_json:
            sys.stdout.write("\n")
        return exit_code_for(events)
    finally:
        await repl.llm_service.aclose()


async def run_plain_terminal(repl: FinAIRepl) -> None:
    """Run the line-oriented terminal when a TTY is unavailable."""
    try:
        await repl.run()
    finally:
        await repl.llm_service.aclose()


def build_app(repl: FinAIRepl) -> FinAIApp:
    """Create the Textual shell wired to the REPL's current session."""
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
    # Late-bound: /new and resume replace repl.store.
    app.clear_pending_callback = lambda: repl.store.clear_pending()

    async def stream(query: str):
        repl.mode = app.mode
        async for event in repl.typed_stream(query):
            yield event

    app.event_stream = stream
    return app


async def run_interactive(repl: FinAIRepl) -> None:
    """Start the Textual shell and connect it to the session stream."""
    app = build_app(repl)
    try:
        await app.run_async()
    finally:
        await repl.llm_service.aclose()


def main() -> None:
    args = parse_arguments()
    try:
        # Keep stdout clean for --json/--plain: tracing diagnostics go to stderr.
        tracing = quiet_stdout(initialize_tracing)
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
            code = asyncio.run(
                run_one_shot(repl, " ".join(args.query), as_json=args.json)
            )
            quiet_stdout(tracing.shutdown)
            sys.exit(code)
        if sys.stdin.isatty() and sys.stdout.isatty():
            asyncio.run(run_interactive(repl))
        else:
            asyncio.run(run_plain_terminal(repl))
        tracing.shutdown()
    except MissingOpenRouterKeyError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(EXIT_FAILED)
    except KeyboardInterrupt:
        sys.exit(130)
