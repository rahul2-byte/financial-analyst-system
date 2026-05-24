import inspect
from collections.abc import AsyncGenerator

import pytest


def test_observe_tracks_sync_functions_that_return_async_generators(monkeypatch):
    import app.core.observability as obs

    tracking_state = {"active": 0}
    lifecycle: list[tuple[str, int]] = []

    class _MockOpikContext:
        def update_current_span(self, metadata=None):
            return None

    def _fake_track(name=None):
        def _decorate(func):
            if inspect.isasyncgenfunction(func):
                async def _wrapped(*args, **kwargs):
                    tracking_state["active"] += 1
                    lifecycle.append(("enter", tracking_state["active"]))
                    try:
                        async for item in func(*args, **kwargs):
                            yield item
                    finally:
                        lifecycle.append(("exit", tracking_state["active"]))
                        tracking_state["active"] -= 1

                return _wrapped

            if inspect.iscoroutinefunction(func):
                async def _wrapped(*args, **kwargs):
                    tracking_state["active"] += 1
                    lifecycle.append(("enter", tracking_state["active"]))
                    try:
                        return await func(*args, **kwargs)
                    finally:
                        lifecycle.append(("exit", tracking_state["active"]))
                        tracking_state["active"] -= 1

                return _wrapped

            def _wrapped(*args, **kwargs):
                tracking_state["active"] += 1
                lifecycle.append(("enter", tracking_state["active"]))
                try:
                    return func(*args, **kwargs)
                finally:
                    lifecycle.append(("exit", tracking_state["active"]))
                    tracking_state["active"] -= 1

            return _wrapped

        return _decorate

    monkeypatch.setattr(obs, "opik_context", _MockOpikContext())
    monkeypatch.setattr(obs.opik, "track", _fake_track)

    seen_active_counts: list[int] = []

    @obs.observe(name="test-stream")
    def build_stream() -> AsyncGenerator[str, None]:
        async def _generator():
            seen_active_counts.append(tracking_state["active"])
            yield "token-1"
            seen_active_counts.append(tracking_state["active"])
            yield "token-2"

        return _generator()

    async def _consume() -> list[str]:
        return [item async for item in build_stream()]

    import asyncio

    assert asyncio.run(_consume()) == ["token-1", "token-2"]
    assert seen_active_counts == [1, 1]
    assert lifecycle == [("enter", 1), ("exit", 1), ("enter", 1), ("exit", 1)]


def test_observe_tracks_sync_async_generator_setup_failures(monkeypatch):
    import app.core.observability as obs

    tracking_state = {"active": 0}
    lifecycle: list[tuple[str, int]] = []

    class _MockOpikContext:
        def update_current_span(self, metadata=None):
            return None

    def _fake_track(name=None):
        def _decorate(func):
            if inspect.isasyncgenfunction(func):
                async def _wrapped(*args, **kwargs):
                    tracking_state["active"] += 1
                    lifecycle.append(("enter", tracking_state["active"]))
                    try:
                        async for item in func(*args, **kwargs):
                            yield item
                    finally:
                        lifecycle.append(("exit", tracking_state["active"]))
                        tracking_state["active"] -= 1

                return _wrapped

            if inspect.iscoroutinefunction(func):
                async def _wrapped(*args, **kwargs):
                    tracking_state["active"] += 1
                    lifecycle.append(("enter", tracking_state["active"]))
                    try:
                        return await func(*args, **kwargs)
                    finally:
                        lifecycle.append(("exit", tracking_state["active"]))
                        tracking_state["active"] -= 1

                return _wrapped

            def _wrapped(*args, **kwargs):
                tracking_state["active"] += 1
                lifecycle.append(("enter", tracking_state["active"]))
                try:
                    return func(*args, **kwargs)
                finally:
                    lifecycle.append(("exit", tracking_state["active"]))
                    tracking_state["active"] -= 1

            return _wrapped

        return _decorate

    monkeypatch.setattr(obs, "opik_context", _MockOpikContext())
    monkeypatch.setattr(obs.opik, "track", _fake_track)

    @obs.observe(name="test-stream")
    def build_stream() -> AsyncGenerator[str, None]:
        raise RuntimeError("setup failed")

    with pytest.raises(RuntimeError, match="setup failed"):
        build_stream()

    assert lifecycle == [("enter", 1), ("exit", 1)]
