from __future__ import annotations

import pytest
from app.routes import health
from app.services.llm_interface import LLMServiceInterface


class _HealthyLLM(LLMServiceInterface):
    async def generate_stream(self, messages, model, **kwargs):
        if False:
            yield {"messages": messages, "model": model, "kwargs": kwargs}

    async def check_health(self) -> bool:
        return True

    async def generate(self, messages, model, **kwargs):
        raise NotImplementedError

    async def generate_message(self, messages, model, **kwargs):
        raise NotImplementedError


@pytest.mark.asyncio
async def test_health_route_reports_components_and_both_canaries(monkeypatch) -> None:
    monkeypatch.setattr("app.routes.health._check_market_data_readiness", lambda: True)

    async def _internal_canary():
        return {"status": "ok", "details": {"query_normalization": "ok"}}

    async def _external_canary():
        return {"status": "ok", "details": {"tinyfish_search": "ok"}}

    monkeypatch.setattr("app.routes.health._run_internal_canary", _internal_canary)
    monkeypatch.setattr("app.routes.health._run_external_canary", _external_canary)

    payload = await health.health_check(llm_service=_HealthyLLM())

    assert payload["status"] == "healthy"
    assert payload["components"]["llm_service"] == "up"
    assert payload["components"]["market_data"] == "up"
    assert payload["canaries"]["internal"]["status"] == "ok"
    assert payload["canaries"]["external"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_route_keeps_core_health_green_when_external_canary_degrades(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.routes.health._check_market_data_readiness", lambda: True)

    async def _internal_canary():
        return {"status": "ok", "details": {"query_normalization": "ok"}}

    async def _external_canary():
        return {"status": "degraded", "details": {"tinyfish_search": "timeout"}}

    monkeypatch.setattr("app.routes.health._run_internal_canary", _internal_canary)
    monkeypatch.setattr("app.routes.health._run_external_canary", _external_canary)

    payload = await health.health_check(llm_service=_HealthyLLM())

    assert payload["status"] == "healthy"
    assert payload["canaries"]["external"]["status"] == "degraded"
