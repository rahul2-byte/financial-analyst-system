# Migrate to Opik Tracing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completely replace the existing Phoenix/OpenTelemetry setup with a local-only Opik installation for rich, LLM-native tracing and evaluation across all agents.

**Architecture:** Remove manual OpenTelemetry boilerplate and use Opik's native Python SDK (`opik.configure(use_local=True)` and `@opik.track`). The existing `@observe` decorator and `langfuse_context` mock in `observability.py` will be rewritten to act as a bridge to Opik, meaning we won't need to modify every individual agent file.

**Tech Stack:** Python, Opik SDK

---

### Task 1: Add Opik Dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add opik to requirements**
Add `opik` to the requirements file.

```text
opik>=1.0.0
```

- [ ] **Step 2: Commit**
```bash
git add backend/requirements.txt
git commit -m "build(deps): add opik sdk for observability"
```

### Task 2: Update Configuration Models

**Files:**
- Modify: `backend/app/config/models.py`

- [ ] **Step 1: Remove Phoenix config and add Opik config**
Modify the settings class to remove `PHOENIX_HOST` and replace it with Opik configuration.

```python
    # Remove:
    # LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    # PHOENIX_HOST: str = "http://localhost:6006"
    
    # Add this:
    OPIK_USE_LOCAL: bool = True
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/config/models.py
git commit -m "refactor(config): switch observability config from phoenix to opik"
```

### Task 3: Refactor Observability Core

**Files:**
- Modify: `backend/app/core/observability.py`

- [ ] **Step 1: Replace OpenTelemetry setup with Opik**
Rewrite `observability.py` to initialize Opik locally and expose the `@observe` decorator as a wrapper around `@opik.track`. Ensure `langfuse_context` bridges to `opik.opik_context`.

```python
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
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/core/observability.py
git commit -m "feat(observability): bridge core decorators to use Opik SDK"
```

### Task 4: Clean up App Initialization

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Remove OpenTelemetry HTTP/FastAPI instrumentors**
Remove the manual FastAPI/HTTPX instrumentors from `main.py` that were previously used for Phoenix.

Remove these lines:
```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/main.py
git commit -m "refactor(main): remove legacy opentelemetry instrumentors"
```
