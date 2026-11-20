from __future__ import annotations

import sys
import time
import types
from typing import Any

import pytest
from app.observability import tracing


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tracing, "_handle", tracing.TracingHandle(enabled=False))
    monkeypatch.setattr("app.config.settings.FINAI_OBSERVABILITY_ENABLED", True)
    monkeypatch.setattr(tracing, "_instrument_httpx", lambda _p: None)


def _fake_phoenix(monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, Any]]):
    otel = types.ModuleType("phoenix.otel")

    def register(**kwargs: Any) -> object:
        calls.append(kwargs)
        return object()

    otel.register = register  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "phoenix.otel", otel)


def test_unreachable_collector_registers_no_exporter(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    _fake_phoenix(monkeypatch, calls)
    monkeypatch.setattr(tracing, "collector_reachable", lambda *_a, **_k: False)

    handle = tracing.initialize_tracing()

    assert handle.enabled is False
    assert calls == []
    start = time.monotonic()
    handle.shutdown()
    assert time.monotonic() - start < 1.0


def test_closed_loopback_port_is_unreachable() -> None:
    assert tracing.collector_reachable("http://127.0.0.1:1/v1/traces") is False


def test_reachable_collector_registers_exporter(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    _fake_phoenix(monkeypatch, calls)
    monkeypatch.setattr(tracing, "collector_reachable", lambda *_a, **_k: True)

    handle = tracing.initialize_tracing()

    assert handle.enabled is True
    assert len(calls) == 1
    assert calls[0]["endpoint"] == "http://127.0.0.1:6006/v1/traces"


def test_shutdown_is_bounded_when_provider_hangs() -> None:
    class Hung:
        def force_flush(self, timeout_millis: int = 0) -> bool:
            time.sleep(5)
            return False

        def shutdown(self) -> None:
            time.sleep(5)

    start = time.monotonic()
    tracing.TracingHandle(enabled=True, provider=Hung()).shutdown()
    assert time.monotonic() - start < 1.3
