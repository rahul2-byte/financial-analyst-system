import os
import logging
import functools
import inspect
import json
from typing import Any, Optional

# OpenTelemetry Imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)

# --- Initialization ---
PHOENIX_HOST = os.getenv("PHOENIX_HOST", "http://localhost:6006")
PHOENIX_ENDPOINT = f"{PHOENIX_HOST}/v1/traces"

# Initialize Tracer
resource = Resource(attributes={"service.name": "financial-intelligence-platform"})
tracer_provider = TracerProvider(resource=resource)
try:
    exporter = OTLPSpanExporter(endpoint=PHOENIX_ENDPOINT)
    span_processor = BatchSpanProcessor(exporter)
    tracer_provider.add_span_processor(span_processor)
    trace.set_tracer_provider(tracer_provider)
    logger.info(f"Arize Phoenix observability initialized at {PHOENIX_HOST}")
except Exception as e:
    logger.error(f"Failed to initialize Phoenix exporter: {e}")

tracer = trace.get_tracer(__name__)

# --- Compatibility Wrappers ---


def observe(name: Optional[Any] = None, as_type: str = "span", **outer_kwargs):
    """
    Bridge decorator: Maps @observe to OpenTelemetry Spans.
    Supports both @observe and @observe(name="...")
    """
    # Handle case where decorator is used without parens: @observe
    if callable(name) and not outer_kwargs:
        func = name
        return observe()(func)

    def decorator(func):
        # Determine span name intelligently
        if name and isinstance(name, str):
            span_name = name
        else:
            # Try to get class name if it's a method
            class_name = ""
            if hasattr(func, "__qualname__") and "." in func.__qualname__:
                class_name = func.__qualname__.split(".")[0]

            if class_name:
                span_name = f"{class_name}:{func.__name__}"
            else:
                span_name = func.__name__

        @functools.wraps(func)
        async def async_generator_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("observation.type", as_type)
                for k, v in outer_kwargs.items():
                    span.set_attribute(f"meta.{k}", str(v))
                
                try:
                    async for item in func(*args, **kwargs):
                        yield item
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("observation.type", as_type)
                for k, v in outer_kwargs.items():
                    span.set_attribute(f"meta.{k}", str(v))

                try:
                    result = await func(*args, **kwargs)
                    if result is not None:
                        span.set_attribute("output.value", str(result))
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("observation.type", as_type)
                for k, v in outer_kwargs.items():
                    span.set_attribute(f"meta.{k}", str(v))

                try:
                    result = func(*args, **kwargs)
                    if result is not None:
                        span.set_attribute("output.value", str(result))
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        if inspect.isasyncgenfunction(func):
            return async_generator_wrapper
        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper

    return decorator


class PhoenixContextWrapper:
    """Bridges langfuse_context calls to OpenTelemetry current span."""

    def update_current_trace(self, **kwargs):
        span = trace.get_current_span()
        if span.is_recording():
            for k, v in kwargs.items():
                val = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                span.set_attribute(f"trace.{k}", val)

    def update_current_observation(self, **kwargs):
        span = trace.get_current_span()
        if span.is_recording():
            # Special handling for LLM inputs/outputs to show up nicely in Phoenix
            if "input" in kwargs:
                input_val = kwargs["input"]
                span.set_attribute(
                    "llm.input",
                    (
                        json.dumps(input_val)
                        if isinstance(input_val, (dict, list))
                        else str(input_val)
                    ),
                )
            if "output" in kwargs:
                output_val = kwargs["output"]
                span.set_attribute(
                    "llm.output",
                    (
                        json.dumps(output_val)
                        if isinstance(output_val, (dict, list))
                        else str(output_val)
                    ),
                )

            # Map usage/usage_details to OTel attributes
            usage = kwargs.get("usage") or kwargs.get("usage_details")
            if usage and isinstance(usage, dict):
                span.set_attribute(
                    "llm.usage.total_tokens", usage.get("total_tokens", 0)
                )
                span.set_attribute(
                    "llm.usage.prompt_tokens",
                    usage.get("prompt_tokens", usage.get("input_tokens", 0)),
                )
                span.set_attribute(
                    "llm.usage.completion_tokens",
                    usage.get("completion_tokens", usage.get("output_tokens", 0)),
                )

            # General attributes
            for k, v in kwargs.items():
                if k not in ["input", "output", "usage", "usage_details", "as_type"]:
                    val = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                    span.set_attribute(f"observation.{k}", val)

    def auth(self, *args, **kwargs):
        pass

    def get_current_trace_id(self):
        span = trace.get_current_span()
        return format(span.get_span_context().trace_id, "032x")


# Global instances
langfuse_context = PhoenixContextWrapper()


def get_langfuse():
    """Mock for the main.py flush logic."""

    class Flusher:
        def flush(self):
            tracer_provider.force_flush()

    return Flusher()
