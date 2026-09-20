from __future__ import annotations

import asyncio
import json

import httpx
from app.models.routing import ExecutionMode, ModelTier, RoutePlan
from app.services.jev_service import JevService
from app.services.routing_policy import RoutingPolicy


def test_deterministic_lookup_route_avoids_model() -> None:
    policy = RoutingPolicy(jev=None)

    route = asyncio.run(
        policy.decide(
            "What is the current price of TCS?",
            available_tools={"data:fetch_stock_data"},
            available_skills=set(),
        )
    )

    assert route.execution_mode is ExecutionMode.TOOL_ONLY
    assert route.model_tier is ModelTier.NONE
    assert route.required_tools == ["data:fetch_stock_data"]
    assert route.confidence == 1.0


def test_jev_unavailable_uses_safe_main_model_fallback() -> None:
    policy = RoutingPolicy(jev=None)

    route = asyncio.run(
        policy.decide(
            "Analyse HDFC Bank and write a full investment report.",
            available_tools={"data:fetch_fundamentals", "news:fetch_news"},
            available_skills={"equity-research"},
        )
    )

    assert route.execution_mode is ExecutionMode.REPORT_SYNTHESIS
    assert route.model_tier is ModelTier.MAIN
    assert route.requires_main_model is True
    assert "router_unavailable" in route.reason_codes


def test_route_plan_rejects_unknown_tools() -> None:
    try:
        RoutePlan(
            execution_mode=ExecutionMode.TOOL_ONLY,
            model_tier=ModelTier.NONE,
            required_tools=["missing:tool"],
            allowed_tools={"data:fetch_stock_data"},
        )
    except ValueError as exc:
        assert "unknown required tool" in str(exc)
    else:
        raise AssertionError("RoutePlan accepted an unknown tool")


def test_jev_choice_is_mapped_to_a_validated_route() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/systemone"
        assert request.headers["authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "jev-latest"
        assert "available_tools" in body["state"]
        return httpx.Response(
            200,
            json={
                "model": "jev-latest",
                "answers": {
                    "route": {
                        "type": "choice",
                        "choice": "tool_market",
                        "probabilities": {"tool_market": 0.97, "report": 0.03},
                        "confidence": 0.97,
                    }
                },
                "usage": {"input_tokens": 10, "output_tokens": 2},
            },
        )

    jev = JevService(
        api_key="test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    route = asyncio.run(
        jev.decide(
            {
                "query": "What is TCS price?",
                "normalized_query": "What is TCS price?",
                "available_tools": ["data:fetch_stock_data"],
                "available_skills": [],
            }
        )
    )

    assert route.execution_mode is ExecutionMode.TOOL_ONLY
    assert route.model_tier is ModelTier.NONE
    assert route.confidence == 0.97


def test_jev_invalid_response_fails_closed() -> None:
    jev = JevService(
        api_key="test-key",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
        ),
    )

    try:
        asyncio.run(jev.decide({"query": "hello"}))
    except RuntimeError as exc:
        assert "route" in str(exc)
    else:
        raise AssertionError("invalid Jev response did not fail")
