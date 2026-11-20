"""Optional OpenTelemetry setup and safe values for local Phoenix traces."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.core.diagnostics import diagnostics_enabled
from app.security.policy import redact_secrets

logger = logging.getLogger(__name__)


def redact_trace_value(value: Any) -> Any:
    """Recursively remove credentials while preserving safe diagnostic values."""
    return redact_secrets(value)


def trace_content(value: Any) -> tuple[str, bool, int]:
    """Return bounded JSON content, truncation state, and original byte count."""
    if settings.FINAI_TRACE_CONTENT == "metadata":
        return "", False, 0
    encoded = json.dumps(
        redact_trace_value(value), ensure_ascii=False, default=str, sort_keys=True
    )
    size = len(encoded.encode("utf-8"))
    limit = max(1, int(settings.FINAI_TRACE_MAX_CONTENT_BYTES))
    if size <= limit:
        return encoded, False, size
    clipped = encoded.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
    return clipped + "…", True, size


@dataclass(frozen=True)
class TracingHandle:
    enabled: bool
    provider: Any | None = None

    def tracer(self, name: str) -> Any | None:
        if not self.enabled:
            return None
        from opentelemetry import trace

        return trace.get_tracer(name)

    def shutdown(self) -> None:
        if self.provider is not None:
            try:
                self.provider.shutdown()
            except Exception:
                logger.exception("Phoenix tracing shutdown failed")


class _NoopSpan:
    def set_attribute(self, _key: str, _value: Any) -> None:
        return None

    def set_attributes(self, _attributes: Mapping[str, Any]) -> None:
        return None

    def add_event(
        self, _name: str, attributes: Mapping[str, Any] | None = None
    ) -> None:
        return None

    def record_exception(self, _exception: BaseException) -> None:
        return None

    def set_status(self, _status: Any) -> None:
        return None

    def end(self) -> None:
        return None


_NOOP_SPAN = _NoopSpan()


_handle = TracingHandle(enabled=False)
_instrumented = False


def initialize_tracing() -> TracingHandle:
    """Initialize Phoenix tracing once; return a disabled handle on failure."""
    global _handle
    if _handle.enabled or not settings.FINAI_OBSERVABILITY_ENABLED:
        return _handle
    try:
        from phoenix.otel import register

        sample_rate = min(1.0, max(0.0, float(settings.FINAI_TRACE_SAMPLE_RATE)))
        if sample_rate < 1.0:
            os.environ.setdefault("OTEL_TRACES_SAMPLER", "traceidratio")
            os.environ.setdefault("OTEL_TRACES_SAMPLER_ARG", str(sample_rate))

        # Phoenix prints a banner on stdout; keep stdout clean for --json/--plain.
        with contextlib.redirect_stdout(sys.stderr):
            provider = register(
                endpoint=settings.FINAI_PHOENIX_ENDPOINT,
                protocol="http/protobuf",
                project_name=settings.FINAI_PHOENIX_PROJECT,
                batch=True,
                auto_instrument=False,
                # verbose=True prints the Phoenix banner; only show it when
                # FINAI diagnostics are explicitly on.
                verbose=diagnostics_enabled(),
            )
    except Exception:
        logger.exception("Phoenix tracing setup failed; continuing without tracing")
        return _handle
    _handle = TracingHandle(enabled=True, provider=provider)
    _instrument_httpx(provider)
    return _handle


def _instrument_httpx(provider: Any) -> None:
    global _instrumented
    if _instrumented:
        return
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument(tracer_provider=provider)
        _instrumented = True
    except Exception:
        logger.exception("HTTPX tracing instrumentation failed; continuing without it")


def tracing_handle() -> TracingHandle:
    return _handle


@contextmanager
def span(name: str, attributes: Mapping[str, Any] | None = None):
    """Start a span when enabled and otherwise preserve the call path."""
    handle = tracing_handle()
    tracer = handle.tracer("finai") if handle.enabled else None
    if tracer is None:
        yield _NOOP_SPAN
        return
    span_attributes = dict(attributes or {})
    if name.startswith("llm."):
        span_attributes.setdefault("openinference.span.kind", "LLM")
    elif name.startswith("tool."):
        span_attributes.setdefault("openinference.span.kind", "TOOL")
    with tracer.start_as_current_span(name, attributes=span_attributes) as current:
        yield current


def record_exception(span_object: Any, error: BaseException) -> None:
    span_object.record_exception(error)
    try:
        from opentelemetry.trace import Status, StatusCode

        span_object.set_status(Status(StatusCode.ERROR, str(error)))
    except Exception:  # noqa: BLE001 - telemetry must not break the app
        return


def mark_success(span_object: Any) -> None:
    try:
        from opentelemetry.trace import Status, StatusCode

        span_object.set_status(Status(StatusCode.OK))
    except Exception:  # noqa: BLE001 - telemetry must not break the app
        return


def current_trace_ids() -> dict[str, str]:
    """Return trace/span IDs for structured log correlation."""
    try:
        from opentelemetry import trace

        context = trace.get_current_span().get_span_context()
        if not context.is_valid:
            return {}
        return {
            "trace_id": format(context.trace_id, "032x"),
            "span_id": format(context.span_id, "016x"),
        }
    except Exception:  # noqa: BLE001 - telemetry must not break the app
        return {}


def set_current_span_attributes(attributes: Mapping[str, Any]) -> None:
    try:
        from opentelemetry import trace

        trace.get_current_span().set_attributes(dict(attributes))
    except Exception:  # noqa: BLE001 - telemetry must not break the app
        return


def add_current_span_event(
    name: str, attributes: Mapping[str, Any] | None = None
) -> None:
    try:
        from opentelemetry import trace

        trace.get_current_span().add_event(name, attributes=dict(attributes or {}))
    except Exception:  # noqa: BLE001 - telemetry must not break the app
        return
