"""Pydantic models for the FIN-AI TypeScript bridge wire protocol (v1).

The models are documented in ``docs/frontend.md``.
Request params are strict (``extra="forbid"``) so client bugs surface during
validation. Results, notifications and display payloads allow unknown fields
for forward compatibility.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from app.events.models import ResearchEvent
from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = 1

RunMode = Literal["guided", "review", "autonomous"]
RunOutcome = Literal["completed", "failed", "cancelled", "clarification", "error"]
LogLevel = Literal["debug", "info", "warning", "error"]

# JSON-RPC 2.0 standard error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Bridge specific error codes.
RUN_IN_PROGRESS = -32001
NO_ACTIVE_RUN = -32002
SESSION_NOT_FOUND = -32003
PROTOCOL_MISMATCH = -32004


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _OpenModel(BaseModel):
    model_config = ConfigDict(extra="allow")


# --- Shared data objects ---------------------------------------------------


class ClientInfo(_Params):
    name: str
    version: str


class TerminalInfo(_Params):
    columns: int = Field(ge=1)
    rows: int = Field(ge=1)


class ModelInfo(_OpenModel):
    id: str
    fallback_id: str | None = None


class SessionInfo(_OpenModel):
    id: str
    title: str
    message_count: int
    run_count: int


class SessionSummary(_OpenModel):
    """Shape returned by ``SessionStore.list_sessions``."""

    id: str
    title: str
    message_count: int
    run_count: int
    last_status: str
    last_activity: str


class DisplaySource(_OpenModel):
    label: str
    url: str
    host: str | None = None


class DisplayCandidate(_OpenModel):
    symbol: str
    name: str
    exchange: str


class Display(_OpenModel):
    """Sanitized, presentation-ready strings computed by the Python runtime."""

    label: str | None = None
    noun: str | None = None
    detail: str | None = None
    failure_detail: str | None = None
    notice: str | None = None
    friendly: str | None = None
    sources: list[DisplaySource] | None = None
    candidates: list[DisplayCandidate] | None = None
    lines: list[str] | None = None
    review_unavailable: bool | None = None
    review_note: str | None = None
    instrument: str | None = None
    failed_nouns: list[str] | None = None


# --- Structured report payload (optional, additive on run.finished) --------

Direction = Literal["up", "down", "flat"]
SignalDirection = Literal["bullish", "bearish", "neutral", "unavailable"]
Importance = Literal["major", "supporting", "minor"]


class ReportInstrument(_OpenModel):
    symbol: str
    name: str | None = None
    exchange: str | None = None


class ReportQuote(_OpenModel):
    price_text: str
    change_text: str | None = None
    direction: Direction | None = None
    as_of_text: str | None = None


class ReportSparkline(_OpenModel):
    """Closing prices resampled to at most 48 points and scaled to 0..1 in Python."""

    points: list[float] = Field(min_length=2, max_length=48)
    period_text: str
    low_text: str
    high_text: str


class ReportSourceStatus(_OpenModel):
    name: str
    status: Literal["available", "degraded", "unavailable"]
    reason: str | None = None


class ReportEvidence(_OpenModel):
    status: Literal["complete", "limited"]
    sources: list[ReportSourceStatus] = Field(default_factory=list)
    observed_through_text: str | None = None


class ReportKeyFigure(_OpenModel):
    label: str
    value_text: str
    as_of_text: str | None = None
    source_ref: int | None = None


class ReportSignal(_OpenModel):
    name: str
    value_text: str
    direction: SignalDirection
    state_text: str | None = None
    strength: float | None = Field(default=None, ge=0, le=1)
    percentile_text: str | None = None


class ReportDriver(_OpenModel):
    text: str
    importance: Importance
    source_refs: list[int] = Field(default_factory=list)


class ReportRisk(_OpenModel):
    text: str
    source_refs: list[int] = Field(default_factory=list)


class ReportSource(DisplaySource):
    ref: int
    retrieved_text: str | None = None
    freshness_text: str | None = None
    trust: str | None = None


class ReportView(_OpenModel):
    """Display-ready report. Every ``*_text`` field is final text from Python."""

    kind: Literal["report", "lookup"]
    instrument: ReportInstrument | None = None
    quote: ReportQuote | None = None
    sparkline: ReportSparkline | None = None
    evidence: ReportEvidence
    stance_text: str | None = None
    summary: str
    key_figures: list[ReportKeyFigure] = Field(default_factory=list)
    signals: list[ReportSignal] = Field(default_factory=list)
    drivers: list[ReportDriver] = Field(default_factory=list)
    risks: list[ReportRisk] = Field(default_factory=list)
    final_view: str | None = None
    detailed_analysis: str | None = None
    limitations: list[str] = Field(default_factory=list)
    sources: list[ReportSource] = Field(default_factory=list)
    disclaimer: str


# --- Method params and results ---------------------------------------------


class InitializeParams(_Params):
    protocol_version: int
    client: ClientInfo
    terminal: TerminalInfo


class InitializeResult(_OpenModel):
    protocol_version: int
    server_version: str
    session: SessionInfo
    mode: RunMode
    data_dir: str
    model: ModelInfo | None = None


class RunStartParams(_Params):
    client_run_id: str
    query: str
    mode: RunMode


class RunStartResult(_OpenModel):
    accepted: Literal[True] = True


class RunCancelParams(_Params):
    client_run_id: str


class RunCancelResult(_OpenModel):
    cancelled: bool


class SessionNewParams(_Params):
    pass


class SessionNewResult(_OpenModel):
    session: SessionInfo


class SessionResumeParams(_Params):
    id_prefix: str


class SessionResumeResult(_OpenModel):
    session: SessionInfo


class SessionListParams(_Params):
    limit: int = Field(default=50, ge=1)


class SessionListResult(_OpenModel):
    sessions: list[SessionSummary]


class SessionHistoryParams(_Params):
    pass


class SessionHistoryResult(_OpenModel):
    queries: list[str]


class ContextInfoParams(_Params):
    pass


class ContextInfoResult(_OpenModel):
    """Free-form output of the ``ContextBudget`` used by ``/context``."""


class ContextCompactParams(_Params):
    pass


class ContextCompactResult(_OpenModel):
    """Free-form result of ``FinAIRepl.compact_context()``."""


class TraceTailParams(_Params):
    limit: int = Field(default=12, ge=1)


class TraceTailResult(_OpenModel):
    records: list[dict[str, Any]]
    ledger_path: str


class ShutdownParams(_Params):
    pass


class ShutdownResult(_OpenModel):
    pass


# --- Notifications (Python -> TS) ------------------------------------------


class RunEventParams(_OpenModel):
    client_run_id: str
    event: ResearchEvent
    display: Display | None


class RunFinishedParams(_OpenModel):
    client_run_id: str
    outcome: RunOutcome
    run_id: UUID | None
    artifact_path: str | None
    message: str | None
    report: ReportView | None = None
    evidence_status: str | None = None
    evidence_availability: list[ReportSourceStatus] | None = None


class BridgeLogParams(_OpenModel):
    level: LogLevel
    message: str


# --- JSON-RPC 2.0 envelopes ------------------------------------------------


class ErrorObject(_OpenModel):
    code: int
    message: str
    data: dict[str, Any] | None = None


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    id: int
    method: str
    params: dict[str, Any] | None = None


class Response(_OpenModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int
    result: dict[str, Any] | None = None
    error: ErrorObject | None = None


class Notification(_OpenModel):
    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: dict[str, Any] | None = None


PROTOCOL_MODELS: tuple[type[BaseModel], ...] = (
    ClientInfo,
    TerminalInfo,
    ModelInfo,
    SessionInfo,
    SessionSummary,
    DisplaySource,
    DisplayCandidate,
    Display,
    ReportInstrument,
    ReportQuote,
    ReportSparkline,
    ReportSourceStatus,
    ReportEvidence,
    ReportKeyFigure,
    ReportSignal,
    ReportDriver,
    ReportRisk,
    ReportSource,
    ReportView,
    InitializeParams,
    InitializeResult,
    RunStartParams,
    RunStartResult,
    RunCancelParams,
    RunCancelResult,
    SessionNewParams,
    SessionNewResult,
    SessionResumeParams,
    SessionResumeResult,
    SessionListParams,
    SessionListResult,
    SessionHistoryParams,
    SessionHistoryResult,
    ContextInfoParams,
    ContextInfoResult,
    ContextCompactParams,
    ContextCompactResult,
    TraceTailParams,
    TraceTailResult,
    ShutdownParams,
    ShutdownResult,
    RunEventParams,
    RunFinishedParams,
    BridgeLogParams,
    ErrorObject,
    Request,
    Response,
    Notification,
)
