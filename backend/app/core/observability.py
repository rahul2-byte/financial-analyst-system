from collections.abc import AsyncGenerator as AsyncGeneratorABC, AsyncIterator as AsyncIteratorABC
import os
import logging
import functools
import inspect
from typing import Any, Optional, get_origin
import opik
from opik import opik_context
from app.config import settings

logger = logging.getLogger(__name__)

# --- Initialization ---
# Opik 2.x requires OPIK_URL_OVERRIDE env var or explicit arg
# Set from our config if not already set
if hasattr(settings, 'OPIK_URL_OVERRIDE') and settings.OPIK_URL_OVERRIDE:
    os.environ.setdefault("OPIK_URL_OVERRIDE", settings.OPIK_URL_OVERRIDE)
if hasattr(settings, 'OPIK_PROJECT_NAME') and settings.OPIK_PROJECT_NAME:
    os.environ.setdefault("OPIK_PROJECT_NAME", settings.OPIK_PROJECT_NAME)

try:
    logger.info(f"Opik observability initialized (url={os.environ.get('OPIK_URL_OVERRIDE')}, project={os.environ.get('OPIK_PROJECT_NAME')}).")
except Exception as e:
    logger.error(f"Failed to setup Opik env vars: {e}")

# --- Compatibility Wrappers ---
def _returns_async_generator(func) -> bool:
    annotation = inspect.signature(func).return_annotation
    origin = get_origin(annotation)
    return origin in {AsyncGeneratorABC, AsyncIteratorABC}


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

        @functools.wraps(func)
        def sync_async_generator_wrapper(*args, **kwargs):
            @opik.track(name=span_name)
            def tracked_setup():
                opik_context.update_current_span(metadata={"observation.type": as_type, **outer_kwargs})
                return func(*args, **kwargs)

            result = tracked_setup()

            @opik.track(name=span_name)
            async def tracked_result():
                opik_context.update_current_span(metadata={"observation.type": as_type, **outer_kwargs})
                async for item in result:
                    yield item

            return tracked_result()

        @opik.track(name=span_name)
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            opik_context.update_current_span(metadata={"observation.type": as_type, **outer_kwargs})
            return func(*args, **kwargs)

        if inspect.isasyncgenfunction(func):
            return async_generator_wrapper
        if _returns_async_generator(func):
            return sync_async_generator_wrapper
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
