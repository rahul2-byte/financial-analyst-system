"""JSON-RPC 2.0 bridge server.

The server speaks the v1 wire protocol over NDJSON. It owns exactly one active
run at a time, enriches every event with a ``Display`` payload, and answers
session/context/trace methods from the same ``FinAIRepl`` the one-shot CLI uses.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from importlib import metadata
from pathlib import Path
from typing import Any, Protocol

from app.config import settings
from finai.bridge import protocol as p
from finai.bridge.framing import NdjsonReader, NdjsonWriter
from finai.context_budget import ContextBudget
from finai.display import build_display, friendly_error
from finai.report_view import build_report_view, evidence_availability
from finai.state import PresentationState, reduce_event
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class ReplLike(Protocol):
    """Surface shared by ``FinAIRepl`` and the bridge's ``FakeRepl``."""

    root: Path
    session_id: str
    mode: str
    history: list[Any]
    store: Any

    def typed_stream(self, query: str) -> AsyncIterator[Any]: ...

    def last_report_material(self) -> dict[str, Any] | None: ...

    def resume_session(self, session_id: str) -> None: ...

    def new_session(self) -> None: ...

    def compact_context(self) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


ReplFactory = Callable[[], ReplLike]
Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class RpcError(Exception):
    """A JSON-RPC error raised by a method handler."""

    def __init__(
        self,
        code: int,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return default


def _params_error(exc: ValidationError) -> dict[str, Any]:
    return {
        "errors": [
            {"loc": list(error["loc"]), "msg": error["msg"]} for error in exc.errors()
        ]
    }


class BridgeServer:
    """Dispatch JSON-RPC requests to one runtime session."""

    def __init__(self, repl_factory: ReplFactory, writer: NdjsonWriter) -> None:
        self._repl_factory = repl_factory
        self._writer = writer
        self._repl: ReplLike | None = None
        self._run_task: asyncio.Task[None] | None = None
        self._run_client_id: str | None = None
        self._shutdown = asyncio.Event()
        self._stop_requested = asyncio.Event()
        self._handlers: dict[str, Handler] = {
            "initialize": self._initialize,
            "run.start": self._run_start,
            "run.cancel": self._run_cancel,
            "session.new": self._session_new,
            "session.resume": self._session_resume,
            "session.list": self._session_list,
            "session.history": self._session_history,
            "context.info": self._context_info,
            "context.compact": self._context_compact,
            "trace.tail": self._trace_tail,
            "shutdown": self._shutdown_method,
        }

    # --- serving -----------------------------------------------------------

    async def serve(self, reader: asyncio.StreamReader) -> None:
        """Read requests until EOF or shutdown; always stop any run."""
        ndjson = NdjsonReader(reader, on_error=self._parse_error)
        try:
            while not self._shutdown.is_set() and not self._stop_requested.is_set():
                read_task = asyncio.ensure_future(ndjson.read())
                stop_wait = asyncio.ensure_future(self._stop_requested.wait())
                done, pending = await asyncio.wait(
                    {read_task, stop_wait}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                if self._shutdown.is_set() or self._stop_requested.is_set():
                    break
                if read_task in done and not read_task.cancelled():
                    request = read_task.result()
                    if request is None:
                        break
                    await self._dispatch(request)
        finally:
            await self.stop()

    def request_stop(self) -> None:
        """Ask ``serve()`` to return after stopping any active run."""
        self._stop_requested.set()

    async def stop(self) -> None:
        """Cancel the active run and wait at most two seconds for its finally."""
        task = self._run_task
        if task is None or task.done():
            return
        task.cancel()
        await asyncio.wait({task}, timeout=2.0)

    async def aclose(self) -> None:
        """Release runtime resources after the protocol loop exits."""
        if self._repl is not None:
            with contextlib.suppress(Exception):
                await self._repl.aclose()

    async def _parse_error(self, code: int, message: str) -> None:
        await self._writer.error(None, code, message)

    async def _dispatch(self, request: dict[str, Any]) -> None:
        raw_id = request.get("id")
        request_id = raw_id if isinstance(raw_id, int) else None
        try:
            envelope = p.Request.model_validate(request)
        except ValidationError as exc:
            await self._writer.error(
                request_id,
                p.INVALID_REQUEST,
                "Invalid request",
                _params_error(exc),
            )
            return

        handler = self._handlers.get(envelope.method)
        if handler is None:
            await self._writer.error(
                envelope.id,
                p.METHOD_NOT_FOUND,
                f"Method not found: {envelope.method}",
            )
            return

        try:
            result = await handler(envelope.params or {})
        except RpcError as exc:
            await self._writer.error(envelope.id, exc.code, exc.message, exc.data)
        except ValidationError as exc:
            await self._writer.error(
                envelope.id,
                p.INVALID_PARAMS,
                "Invalid params",
                _params_error(exc),
            )
        except Exception as exc:  # noqa: BLE001 - boundary: one bad request must not kill the bridge
            logger.exception("bridge method %s failed", envelope.method)
            await self._writer.error(
                envelope.id,
                p.INTERNAL_ERROR,
                f"Internal error: {friendly_error(str(exc))}",
            )
        else:
            await self._writer.result(envelope.id, result)

    # --- helpers -----------------------------------------------------------

    def _require_repl(self) -> ReplLike:
        if self._repl is None:
            raise RpcError(
                p.INTERNAL_ERROR, "Bridge is not initialized; send initialize first"
            )
        return self._repl

    def _active_run(self) -> bool:
        return self._run_task is not None and not self._run_task.done()

    def _refuse_during_run(self) -> None:
        if self._active_run():
            raise RpcError(
                p.RUN_IN_PROGRESS,
                "A run is in progress; finish or cancel it first",
            )

    @staticmethod
    def _server_version() -> str:
        try:
            return metadata.version("financial-analyst-system")
        except metadata.PackageNotFoundError:
            return "0.1.0"

    @staticmethod
    def _session_info(repl: ReplLike) -> p.SessionInfo:
        sessions: list[dict[str, Any]] = []
        with contextlib.suppress(Exception):
            sessions = list(repl.store.list_sessions(repl.root))
        for item in sessions:
            if str(item.get("id")) == repl.session_id:
                return p.SessionInfo(
                    id=str(item.get("id", repl.session_id)),
                    title=str(item.get("title", "New research session")),
                    message_count=_as_int(item.get("message_count")),
                    run_count=_as_int(item.get("run_count")),
                )
        return p.SessionInfo(
            id=repl.session_id,
            title="New research session",
            message_count=0,
            run_count=0,
        )

    # --- methods -----------------------------------------------------------

    async def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        parsed = p.InitializeParams.model_validate(params)
        if parsed.protocol_version != p.PROTOCOL_VERSION:
            raise RpcError(
                p.PROTOCOL_MISMATCH,
                "Protocol version mismatch",
                {"server": p.PROTOCOL_VERSION, "client": parsed.protocol_version},
            )
        # Heavy construction happens here, after the protocol loop exists.
        if self._repl is None:
            self._repl = self._repl_factory()
        repl = self._repl
        return p.InitializeResult(
            protocol_version=p.PROTOCOL_VERSION,
            server_version=self._server_version(),
            session=self._session_info(repl),
            mode=repl.mode,
            data_dir=str(repl.root),
        ).model_dump(mode="json")

    async def _run_start(self, params: dict[str, Any]) -> dict[str, Any]:
        parsed = p.RunStartParams.model_validate(params)
        repl = self._require_repl()
        if self._active_run():
            raise RpcError(
                p.RUN_IN_PROGRESS,
                "A run is already in progress",
            )
        repl.mode = parsed.mode
        self._run_client_id = parsed.client_run_id
        self._run_task = asyncio.create_task(
            self._run(repl, parsed.client_run_id, parsed.query)
        )
        return {"accepted": True}

    async def _run(
        self,
        repl: ReplLike,
        client_run_id: str,
        query: str,
    ) -> None:
        state = PresentationState()
        outcome: p.RunOutcome = "completed"
        artifact_path: str | None = None
        message: str | None = None
        evidence_status: str | None = None
        availability: list[dict[str, Any]] | None = None
        try:
            stream = repl.typed_stream(query)
            async for event in stream:
                state = reduce_event(state, event)
                display = build_display(event, state)
                notification = p.RunEventParams(
                    client_run_id=client_run_id,
                    event=event,
                    display=display,
                )
                await self._writer.notify(
                    "run.event", notification.model_dump(mode="json")
                )
                if event.type == "run.completed":
                    artifact_path = event.artifact_path
                    evidence_status = event.evidence_status
                    availability = list(event.evidence_availability)
                    outcome = (
                        "clarification"
                        if event.terminal_status == "awaiting_clarification"
                        else "completed"
                    )
                elif event.type == "run.failed":
                    outcome = "failed"
                elif event.type == "run.cancelled":
                    outcome = "cancelled"
        except asyncio.CancelledError:
            outcome = "cancelled"
        except Exception as exc:  # noqa: BLE001 - report a friendly boundary error
            logger.exception("run failed client_run_id=%s", client_run_id)
            outcome = "error"
            message = friendly_error(str(exc))
        finally:
            report = self._report_for(repl) if outcome == "completed" else None
            finished = p.RunFinishedParams(
                client_run_id=client_run_id,
                outcome=outcome,
                run_id=state.run_id,
                artifact_path=artifact_path,
                message=message,
                report=report,
                evidence_status=evidence_status,
                evidence_availability=evidence_availability(availability),
            )
            await self._writer.notify("run.finished", finished.model_dump(mode="json"))

    @staticmethod
    def _report_for(repl: ReplLike) -> p.ReportView | None:
        """Structured view for the run just finished; any failure means no view."""
        try:
            material = repl.last_report_material()
        except Exception:  # noqa: BLE001 - presentation must never break a run
            logger.exception("report material unavailable")
            return None
        return build_report_view(material)

    async def _run_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        parsed = p.RunCancelParams.model_validate(params)
        task = self._run_task
        if task is not None and self._run_client_id == parsed.client_run_id:
            if task.done():
                return {"cancelled": False}
            task.cancel()
            return {"cancelled": True}
        if self._run_client_id == parsed.client_run_id:
            return {"cancelled": False}
        raise RpcError(
            p.NO_ACTIVE_RUN,
            f"No active run for client_run_id {parsed.client_run_id}",
        )

    async def _session_new(self, params: dict[str, Any]) -> dict[str, Any]:
        p.SessionNewParams.model_validate(params)
        self._refuse_during_run()
        repl = self._require_repl()
        repl.new_session()
        return {"session": self._session_info(repl).model_dump(mode="json")}

    async def _session_resume(self, params: dict[str, Any]) -> dict[str, Any]:
        parsed = p.SessionResumeParams.model_validate(params)
        self._refuse_during_run()
        repl = self._require_repl()
        sessions = list(repl.store.list_sessions(repl.root))
        matches = [
            item
            for item in sessions
            if str(item.get("id", "")).startswith(parsed.id_prefix)
        ]
        if len(matches) != 1:
            raise RpcError(
                p.SESSION_NOT_FOUND,
                "No unique session matched that prefix",
                {
                    "matches": [
                        {
                            "id": str(item.get("id", "")),
                            "title": str(item.get("title", "")),
                        }
                        for item in matches
                    ]
                },
            )
        session_id = str(matches[0]["id"])
        repl.resume_session(session_id)
        return {"session": self._session_info(repl).model_dump(mode="json")}

    async def _session_list(self, params: dict[str, Any]) -> dict[str, Any]:
        parsed = p.SessionListParams.model_validate(params)
        repl = self._require_repl()
        sessions: list[dict[str, Any]] = []
        with contextlib.suppress(Exception):
            sessions = list(repl.store.list_sessions(repl.root))
        summaries = [
            p.SessionSummary(
                id=str(item.get("id", "")),
                title=str(item.get("title", "")),
                message_count=_as_int(item.get("message_count")),
                run_count=_as_int(item.get("run_count")),
                last_status=str(item.get("last_status", "unknown")),
                last_activity=str(item.get("last_activity", "")),
            )
            for item in sessions[: parsed.limit]
        ]
        return {"sessions": [item.model_dump(mode="json") for item in summaries]}

    async def _session_history(self, params: dict[str, Any]) -> dict[str, Any]:
        p.SessionHistoryParams.model_validate(params)
        repl = self._require_repl()
        queries = [
            str(message.content)
            for message in repl.history
            if getattr(message, "role", None) == "user"
        ]
        return {"queries": queries}

    async def _context_info(self, params: dict[str, Any]) -> dict[str, Any]:
        p.ContextInfoParams.model_validate(params)
        repl = self._require_repl()
        budget = ContextBudget(
            max_tokens=settings.FINAI_CONTEXT_MAX_TOKENS,
            compaction_ratio=settings.FINAI_CONTEXT_COMPACTION_RATIO,
        )
        _, result = budget.compact(list(repl.history))
        estimated = _as_int(result.get("estimated_tokens"))
        stored: dict[str, Any] = {}
        with contextlib.suppress(Exception):
            stored = dict(repl.store.read_context())
        return {
            "message_count": len(repl.history),
            "estimated_tokens": estimated,
            "max_tokens": budget.max_tokens,
            "compaction_limit": budget.compaction_limit,
            "stored": stored,
        }

    async def _context_compact(self, params: dict[str, Any]) -> dict[str, Any]:
        p.ContextCompactParams.model_validate(params)
        self._refuse_during_run()
        repl = self._require_repl()
        return dict(repl.compact_context())

    async def _trace_tail(self, params: dict[str, Any]) -> dict[str, Any]:
        parsed = p.TraceTailParams.model_validate(params)
        repl = self._require_repl()
        records: list[dict[str, Any]] = list(repl.store.trace.read())
        ledger_path = str(repl.store.trace.path)
        return {
            "records": records[-parsed.limit :],
            "ledger_path": ledger_path,
        }

    async def _shutdown_method(self, params: dict[str, Any]) -> dict[str, Any]:
        p.ShutdownParams.model_validate(params)
        self._shutdown.set()
        return {}


__all__ = ["BridgeServer", "ReplLike", "RpcError"]
