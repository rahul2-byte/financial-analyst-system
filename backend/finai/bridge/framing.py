"""NDJSON framing for the FIN-AI bridge.

Reader: UTF-8 newline-delimited JSON over an ``asyncio.StreamReader`` with an
8 MiB line limit. A malformed or oversize line is reported through the
``on_error`` callback (the server turns that into a ``-32700`` response) and
the reader keeps serving. Writer: one compact JSON object per line, serialized
under an ``asyncio.Lock`` and flushed after every line.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

MAX_LINE_BYTES = 8 * 1024 * 1024
_READ_CHUNK = 64 * 1024

ErrorCallback = Callable[[int, str], Awaitable[None]]


class Writable(Protocol):
    """Minimal file-like surface shared by pipes, sockets and test buffers."""

    def write(self, data: bytes) -> int | None: ...

    def flush(self) -> None: ...


class NdjsonReader:
    """Incremental NDJSON line reader with a hard line-size limit."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        *,
        on_error: ErrorCallback | None = None,
        max_line_bytes: int = MAX_LINE_BYTES,
    ) -> None:
        self._reader = reader
        self._on_error = on_error
        self._max_line_bytes = max_line_bytes
        self._buffer = bytearray()

    async def read(self) -> dict[str, Any] | None:
        """Return the next JSON object, or ``None`` on clean end of input.

        Blank lines are skipped. Invalid lines call ``on_error`` and are
        dropped; the next line is still read.
        """
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                raw = bytes(self._buffer[:newline])
                del self._buffer[: newline + 1]
                if raw.endswith(b"\r"):
                    raw = raw[:-1]
                if not raw.strip():
                    continue
                parsed = await self._decode(raw)
                if parsed is not None:
                    return parsed
                continue

            if len(self._buffer) > self._max_line_bytes:
                dropped = await self._drop_oversize_line()
                await self._report(
                    -32700,
                    f"Parse error: line exceeds {self._max_line_bytes} bytes"
                    + (" (dropped)" if dropped else ""),
                )
                continue

            chunk = await self._reader.read(_READ_CHUNK)
            if not chunk:
                if not self._buffer:
                    return None
                raw = bytes(self._buffer)
                self._buffer.clear()
                if not raw.strip():
                    return None
                return await self._decode(raw)
            self._buffer.extend(chunk)

    async def _decode(self, raw: bytes) -> dict[str, Any] | None:
        if len(raw) > self._max_line_bytes:
            await self._report(
                -32700,
                f"Parse error: line exceeds {self._max_line_bytes} bytes",
            )
            return None
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            await self._report(-32700, f"Parse error: invalid UTF-8 ({exc.reason})")
            return None
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            await self._report(-32700, f"Parse error: {exc.msg}")
            return None
        if not isinstance(value, dict):
            await self._report(-32700, "Parse error: expected a JSON object")
            return None
        return value

    async def _drop_oversize_line(self) -> bool:
        """Discard buffered bytes up to and including the next newline."""
        dropped = False
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                del self._buffer[: newline + 1]
                return True
            dropped = True
            self._buffer.clear()
            chunk = await self._reader.read(_READ_CHUNK)
            if not chunk:
                return dropped

    async def _report(self, code: int, message: str) -> None:
        if self._on_error is not None:
            await self._on_error(code, message)


class NdjsonWriter:
    """Serialize JSON-RPC envelopes as compact UTF-8 NDJSON lines."""

    def __init__(self, stream: Writable) -> None:
        self._stream = stream
        self._lock = asyncio.Lock()

    async def send(self, payload: dict[str, Any]) -> None:
        line = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        async with self._lock:
            self._stream.write(line)
            self._stream.flush()

    async def result(self, request_id: int, result: Any) -> None:
        await self.send({"jsonrpc": "2.0", "id": request_id, "result": result})

    async def error(
        self,
        request_id: int | None,
        code: int,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        await self.send({"jsonrpc": "2.0", "id": request_id, "error": error})

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self.send({"jsonrpc": "2.0", "method": method, "params": params})


__all__ = ["MAX_LINE_BYTES", "NdjsonReader", "NdjsonWriter", "Writable"]
