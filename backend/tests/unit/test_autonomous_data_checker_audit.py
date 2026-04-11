import pytest

from agents.financial.data.data_check_node import data_check_node
from app.core.node_resources import resources
from app.core.orchestration_schemas import OfflineStatus


class _StubLLMResponse:
    def __init__(self) -> None:
        self.content = ""
        self.tool_calls = None


class _CountingLLMService:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_message(self, messages, model, tools=None):
        self.calls += 1
        return _StubLLMResponse()


def _set_llm_service(stub):
    previous = resources._llm_service
    setattr(resources, "_llm_service", stub)
    return previous


@pytest.mark.asyncio
async def test_checker_uses_offline_audit_when_data_status_incomplete() -> None:
    stub = _CountingLLMService()
    previous = _set_llm_service(stub)
    try:
        state = {
            "user_query": "Analyze AAPL",
            "goal": {"ticker": "AAPL"},
            "data_status": {},
        }
        await data_check_node(state)
    finally:
        setattr(resources, "_llm_service", previous)

    assert stub.calls >= 1


@pytest.mark.asyncio
async def test_checker_skips_offline_audit_when_data_status_complete() -> None:
    stub = _CountingLLMService()
    previous = _set_llm_service(stub)
    try:
        state = {
            "user_query": "Analyze AAPL",
            "goal": {"ticker": "AAPL"},
            "data_status": {
                "ohlcv": {
                    "by_symbol": {
                        "AAPL": {
                            "available": True,
                            "coverage": 0.95,
                            "freshness": 0.95,
                            "source": "fetch_attempt",
                            "error": None,
                        }
                    },
                    "available": True,
                    "partial": True,
                    "source": "fetch_attempt",
                    "coverage": 0.95,
                    "freshness": 0.95,
                    "error": None,
                },
                "news": {
                    "available": True,
                    "partial": True,
                    "source": "fetch_attempt",
                    "coverage": 0.95,
                    "freshness": 0.95,
                    "error": None,
                },
                "fundamentals": {
                    "by_symbol": {
                        "AAPL": {
                            "available": True,
                            "coverage": 0.95,
                            "freshness": 0.95,
                            "source": "fetch_attempt",
                            "error": None,
                        }
                    },
                    "available": True,
                    "partial": True,
                    "source": "fetch_attempt",
                    "coverage": 0.95,
                    "freshness": 0.95,
                    "error": None,
                },
                "macro": {
                    "available": True,
                    "partial": True,
                    "source": "fetch_attempt",
                    "coverage": 0.95,
                    "freshness": 0.95,
                    "error": None,
                },
            },
        }
        await data_check_node(state)
    finally:
        setattr(resources, "_llm_service", previous)

    assert stub.calls == 0


@pytest.mark.asyncio
async def test_checker_updates_goal_ticker_from_offline_audit(monkeypatch) -> None:
    async def _stub_audit(_ticker: str):
        return (
            OfflineStatus(
                data_available=True,
                ticker_used="AAPL",
                reasoning="Exact symbol found locally",
                extra_info={"latest_date": "2026-04-01", "row_count": 400},
            ),
            [],
        )

    monkeypatch.setattr(
        "agents.financial.data.data_check_node._run_local_offline_audit",
        _stub_audit,
    )

    result = await data_check_node(
        {
            "user_query": "Analyze Apple",
            "goal": {"ticker": "APPLE"},
            "data_status": {},
        }
    )

    assert result["goal"]["ticker"] == "AAPL"
    assert result["data_check"]["local_audit"]["original_ticker"] == "APPLE"
    assert result["data_check"]["local_audit"]["resolved_ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_checker_marks_low_coverage_datasets_for_refresh() -> None:
    result = await data_check_node(
        {
            "user_query": "Analyze AAPL",
            "goal": {"ticker": "AAPL"},
            "timeframe_policy": {
                "ohlcv": {"minimum_coverage_ratio": 0.8},
                "news": {"minimum_coverage_ratio": 0.5},
                "fundamentals": {"minimum_coverage_ratio": 0.75},
                "macro": {"minimum_coverage_ratio": 1.0},
            },
            "data_status": {
                "ohlcv": {
                    "available": True,
                    "coverage": 1.0,
                    "freshness": 0.95,
                },
                "news": {
                    "available": True,
                    "coverage": 1.0,
                    "freshness": 0.95,
                },
                "fundamentals": {
                    "available": True,
                    "coverage": 0.0,
                    "freshness": 0.95,
                },
                "macro": {
                    "available": True,
                    "coverage": 0.0,
                    "freshness": 0.95,
                },
            },
        }
    )

    assert result["status"] == "partial"
    assert result["data_check"]["stale_datasets"] == ["fundamentals", "macro"]
