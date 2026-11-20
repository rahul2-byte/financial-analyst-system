"""Entry point for ``python -m finai.bridge``."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from finai.bridge.fake import FakeRepl
from finai.bridge.framing import MAX_LINE_BYTES, NdjsonWriter, Writable
from finai.bridge.server import BridgeServer

logger = logging.getLogger(__name__)


class FdWriter(Writable):
    """``NdjsonWriter`` target bound to the pre-swap protocol fd."""

    def __init__(self, fd: int) -> None:
        self._fd = fd

    def write(self, data: bytes) -> int:
        view = memoryview(data)
        while view:
            written = os.write(self._fd, view)
            view = view[written:]
        return len(data)

    def flush(self) -> None:
        return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="finai.bridge",
        description="JSON-RPC bridge between the Python runtime and the TS UI.",
    )
    parser.add_argument("--data-dir", type=Path, default=Path(".finai"))
    parser.add_argument("--session", default=None)
    parser.add_argument("--replay-snapshots", type=Path, default=None)
    parser.add_argument("--fake-events", type=Path, default=None)
    parser.add_argument("--fake-delay-ms", type=int, default=0)
    parser.add_argument(
        "--fake-report",
        choices=("full", "partial", "lookup"),
        default=None,
        help="with --fake-events: adapt the stream and attach structured report data",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args(argv)


def _repl_factory(args: argparse.Namespace) -> Callable[[], Any]:
    """Build the repl constructor; the heavy import happens only on demand."""
    if args.fake_events is not None:
        events = FakeRepl.load_events(args.fake_events)
        material = None
        if args.fake_report is not None:
            from finai.bridge.fake_report import fake_events, fake_material

            events = fake_events(events, args.fake_report)
            material = fake_material(args.fake_report)
        root = args.data_dir
        delay_ms = args.fake_delay_ms
        return lambda: FakeRepl(
            events, root=root, delay_ms=delay_ms, material=material
        )

    replay_snapshots: dict[str, str] | None = None
    if args.replay_snapshots is not None:
        replay_snapshots = json.loads(
            args.replay_snapshots.read_text(encoding="utf-8")
        )
        if not isinstance(replay_snapshots, dict):
            raise ValueError("--replay-snapshots must contain a JSON object")
    data_dir = args.data_dir
    session = args.session

    def make_repl() -> Any:
        from finai.session import FinAIRepl  # heavy import; initialize triggers it

        return FinAIRepl(data_dir, session, replay_snapshots)

    return make_repl


async def serve(args: argparse.Namespace, writer: NdjsonWriter) -> None:
    """Serve the protocol until EOF/shutdown; wire stdin and SIGTERM first."""
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=MAX_LINE_BYTES * 2)
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    server = BridgeServer(_repl_factory(args), writer)
    loop.add_signal_handler(signal.SIGTERM, server.request_stop)
    try:
        await server.serve(reader)
    finally:
        await server.aclose()


def main() -> None:
    args = parse_args()
    # The protocol is the only thing on stdout: make fd 1 the stderr fd and
    # keep the real stdout in the protocol fd.
    protocol_fd = os.dup(1)
    os.dup2(2, 1)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    asyncio.run(serve(args, NdjsonWriter(FdWriter(protocol_fd))))


if __name__ == "__main__":
    main()
