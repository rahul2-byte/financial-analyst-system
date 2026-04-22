import logging
import functools
import inspect
from typing import Any, Optional
import opik
from opik import opik_context
from app.config import settings

logger = logging.getLogger(__name__)

# --- Initialization ---
try:
    opik.configure(use_local=settings.OPIK_USE_LOCAL)
    logger.info("Opik observability initialized (local mode).")
except Exception as e:
    logger.error(f"Failed to initialize Opik: {e}")

# --- Compatibility Wrappers ---
def observe(name: Optional[Any] = None, as_type: str = "span", **outer_kwargs):
    """Bridge decorator: Maps legacy @observe to Opik's @opik.track."""
    if callable(name) and not outer_kwargs:
        func = name
        return observe()(func)

    def decorator(func):
        span_name = name if name and isinstance(name, str) else func.__name__
        
        # We wrap the function using opik.track
        @opik.track(name=span_name)
        @functools.wraps(func)
        async def async_generator_wrapper(*args, **kwargs):
            opik_context.update_current_span(metadata={"observation.type": as_type, **outer_kwargs})
            async for item in func(*args, **kwargs):
                yield item

        @opik.track(name=span_name)
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            opik_context.update_current_span(metadata={"observation.type": as_type, **outer_kwargs})
            return await func(*args, **kwargs)

        @opik.track(name=span_name)
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            opik_context.update_current_span(metadata={"observation.type": as_type, **outer_kwargs})
            return func(*args, **kwargs)

        if inspect.isasyncgenfunction(func):
            return async_generator_wrapper
        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper

    return decorator


class OpikContextWrapper:
    """Bridges legacy langfuse_context calls to Opik context."""

    def update_current_trace(self, **kwargs):
        try:
            opik_context.update_current_trace(metadata=kwargs)
        except Exception:
            pass

    def update_current_observation(self, **kwargs):
        try:
            opik_context.update_current_span(metadata=kwargs)
        except Exception:
            pass

    def auth(self, *args, **kwargs):
        pass

    def get_current_trace_id(self):
        try:
            trace_data = opik_context.get_current_trace_data()
            return trace_data.id if trace_data else "unknown"
        except Exception:
            return "unknown"

# Global instances
langfuse_context = OpikContextWrapper()

def get_langfuse():
    """Mock for the main.py flush logic."""
    class Flusher:
        def flush(self):
            pass
    return Flusher()
