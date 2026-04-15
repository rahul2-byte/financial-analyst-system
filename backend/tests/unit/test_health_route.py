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
    monkeypatch.setattr("app.routes.health._check_database_readiness", lambda: True)
    monkeypatch.setattr("app.routes.health._check_embedding_readiness", lambda: True)

    async def _internal_canary():
        return {"status": "ok", "details": {"query_normalization": "ok"}}

    async def _external_canary():
        return {"status": "ok", "details": {"exa_search": "ok"}}

    monkeypatch.setattr("app.routes.health._run_internal_canary", _internal_canary)
    monkeypatch.setattr("app.routes.health._run_external_canary", _external_canary)

    payload = await health.health_check(llm_service=_HealthyLLM())

    assert payload["status"] == "healthy"
    assert payload["components"]["llm_service"] == "up"
    assert payload["components"]["database"] == "up"
    assert payload["components"]["embedding_service"] == "up"
    assert payload["canaries"]["internal"]["status"] == "ok"
    assert payload["canaries"]["external"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_route_keeps_core_health_green_when_external_canary_degrades(monkeypatch) -> None:
    monkeypatch.setattr("app.routes.health._check_database_readiness", lambda: True)
    monkeypatch.setattr("app.routes.health._check_embedding_readiness", lambda: True)

    async def _internal_canary():
        return {"status": "ok", "details": {"query_normalization": "ok"}}

    async def _external_canary():
        return {"status": "degraded", "details": {"exa_search": "timeout"}}

    monkeypatch.setattr("app.routes.health._run_internal_canary", _internal_canary)
    monkeypatch.setattr("app.routes.health._run_external_canary", _external_canary)

    payload = await health.health_check(llm_service=_HealthyLLM())

    assert payload["status"] == "healthy"
    assert payload["canaries"]["external"]["status"] == "degraded"


def test_embedding_readiness_is_false_when_sentence_transformers_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("app.routes.health.embedding_service_module.SentenceTransformer", None)
    monkeypatch.setattr("app.routes.health.EmbeddingService._instance", None)

    assert health._check_embedding_readiness() is False
