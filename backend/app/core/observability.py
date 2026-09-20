"""Small, local-only timing and context helpers for run artifacts."""

from __future__ import annotations

import functools
import inspect
import time
from contextvars import ContextVar
from typing import Any

from app.observability.tracing import mark_success, record_exception, span

_metrics: ContextVar[tuple[dict[str, Any], ...]] = ContextVar(
    "finai_metrics", default=()
)
_context: ContextVar[dict[str, Any] | None] = ContextVar("finai_context", default=None)


def _record(metric: dict[str, Any]) -> None:
    current = _metrics.get()
    _metrics.set((current + (metric,))[-1000:])


def get_recorded_metrics() -> list[dict[str, Any]]:
    return [dict(metric) for metric in _metrics.get()]


def clear_recorded_metrics() -> None:
    _metrics.set(())


def _finish(name: str, as_type: str, started: float, error: Exception | None) -> None:
    _record(
        {
            "name": name,
            "type": as_type,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "status": "error" if error else "ok",
            "error": str(error) if error else None,
        }
    )


def observe(name: str | None = None, as_type: str = "span", **metadata: Any):
    """Record local duration without contacting a telemetry provider."""

    if callable(name) and not metadata:
        return observe()(name)

    def decorator(function):
        metric_name = name if isinstance(name, str) else function.__name__

        if inspect.isasyncgenfunction(function):

            @functools.wraps(function)
            async def async_generator_wrapper(*args, **kwargs):
                started = time.perf_counter()
                error: Exception | None = None
                with span(metric_name, metadata) as trace_span:
                    try:
                        async for item in function(*args, **kwargs):
                            event_type = getattr(item, "type", None)
                            if event_type:
                                trace_span.add_event(
                                    "research.event", {"event.type": event_type}
                                )
                                if event_type == "run.completed":
                                    terminal_status = getattr(
                                        item, "terminal_status", "COMPLETED"
                                    )
                                    availability = getattr(
                                        item, "evidence_availability", []
                                    )
                                    trace_span.set_attributes(
                                        {
                                            "app.execution_status": terminal_status.upper(),
                                            "app.evidence_status": getattr(
                                                item, "evidence_status", None
                                            )
                                            or "unknown",
                                            "app.evidence_sources": len(availability),
                                            "app.evidence_limited": terminal_status
                                            == "completed_with_limited_evidence",
                                        }
                                    )
                                elif event_type == "run.failed":
                                    trace_span.set_attribute(
                                        "app.execution_status", "FAILED"
                                    )
                            yield item
                    except Exception as exc:
                        error = exc
                        record_exception(trace_span, exc)
                        raise
                    else:
                        mark_success(trace_span)
                    finally:
                        _finish(metric_name, as_type, started, error)

            return async_generator_wrapper

        if inspect.iscoroutinefunction(function):

            @functools.wraps(function)
            async def async_wrapper(*args, **kwargs):
                started = time.perf_counter()
                error: Exception | None = None
                with span(metric_name, metadata) as trace_span:
                    try:
                        result = await function(*args, **kwargs)
                    except Exception as exc:
                        error = exc
                        record_exception(trace_span, exc)
                        raise
                    else:
                        mark_success(trace_span)
                        return result
                    finally:
                        _finish(metric_name, as_type, started, error)

            return async_wrapper

        @functools.wraps(function)
        def sync_wrapper(*args, **kwargs):
            started = time.perf_counter()
            error: Exception | None = None
            with span(metric_name, metadata) as trace_span:
                try:
                    result = function(*args, **kwargs)
                except Exception as exc:
                    error = exc
                    record_exception(trace_span, exc)
                    raise
                else:
                    mark_success(trace_span)
                    return result
                finally:
                    _finish(metric_name, as_type, started, error)

        return sync_wrapper

    return decorator


class RunContext:
    def update_current_trace(self, **kwargs: Any) -> None:
        values = dict(_context.get() or {})
        values.update(kwargs)
        _context.set(values)

    def update_current_span(self, **kwargs: Any) -> None:
        self.update_current_trace(**kwargs)

    def get_current_trace_id(self) -> str:
        return str((_context.get() or {}).get("run_id", "unknown"))


run_context = RunContext()
