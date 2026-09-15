from typing import ClassVar

import pytest
from app.core.agent_loop.runtime import RegistryToolRunner
from app.core.resources import RuntimeResources
from app.core.tools.tool_system import tool_executor, tool_registry


class FakeFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def fetch_stock_price(self, ticker: str, period: str, interval: str) -> dict:
        self.calls.append((ticker, period, interval))
        return {
            "ticker": ticker,
            "period": period,
            "interval": interval,
            "data": [
                {"close": 100.0, "high": 101.0, "low": 99.0, "open": 100.0, "volume": 1},
                {"close": 101.0, "high": 102.0, "low": 100.0, "open": 100.0, "volume": 2},
            ],
        }

    def fetch_company_fundamentals(self, ticker: str) -> dict:
        return {
            "ticker": ticker,
            "peRatio": 18.5,
            "priceToBook": 2.2,
            "profitMargins": 0.24,
        }


class FakeRegistry:
    def list_tools(self):
        return []


class FakeExecutor:
    _handlers: ClassVar[dict] = {}


def test_agent_loop_does_not_expose_nested_agent_delegation() -> None:
    runner = RegistryToolRunner(tool_registry, tool_executor)

    exposed_tools = {
        definition["function"]["name"] for definition in runner.definitions()
    }

    assert "analysis:delegate" not in exposed_tools


def test_analysis_tools_request_tickers_not_model_generated_financial_data() -> None:
    runner = RegistryToolRunner(tool_registry, tool_executor)
    definitions = {
        item["function"]["name"]: item["function"]["parameters"]
        for item in runner.definitions()
    }

    for name in ("analysis:run_fundamental_scan", "analysis:run_technical_scan"):
        assert definitions[name]["required"] == ["ticker"]
        assert "raw_data" not in definitions[name]["properties"]
        assert "ohlcv_data" not in definitions[name]["properties"]


@pytest.mark.asyncio
async def test_technical_scan_fetches_missing_ohlcv_from_ticker(monkeypatch) -> None:
    resources = RuntimeResources(llm_service=None, yf_fetcher=FakeFetcher())
    runner = RegistryToolRunner(FakeRegistry(), FakeExecutor(), resources)
    async def direct(callable_, *args):
        return callable_(*args)
    monkeypatch.setattr("app.core.agent_loop.runtime.asyncio.to_thread", direct)
    monkeypatch.setattr("app.core.tools.tool_handlers.technical_scan", lambda args: {"rows": len(args["ohlcv_data"])})

    async def execute_handler(name, args):
        from app.core.tools.tool_handlers import technical_scan

        return type("Result", (), {"to_dict": lambda self: technical_scan(args)})()

    runner.executor.execute_handler = execute_handler

    result = await runner.execute("analysis:run_technical_scan", {"ticker": "HDFCBANK.NS"})

    assert result == {"rows": 2}
    assert resources.yf_fetcher.calls == [("HDFCBANK.NS", "1y", "1d")]


@pytest.mark.asyncio
async def test_stock_fetch_keeps_raw_rows_out_of_model_payload(monkeypatch) -> None:
    resources = RuntimeResources(llm_service=None, yf_fetcher=FakeFetcher())
    runner = RegistryToolRunner(FakeRegistry(), FakeExecutor(), resources)

    async def direct(callable_, *args):
        return callable_(*args)

    monkeypatch.setattr("app.core.agent_loop.runtime.asyncio.to_thread", direct)

    result = await runner.execute("data:fetch_stock_data", {"ticker": "HDFCBANK.NS"})

    assert result["success"] is True
    assert result["data"]["row_count"] == 2
    assert result["data"]["period_return_pct"] == 1.0
    assert "data" not in result["data"]


@pytest.mark.asyncio
async def test_technical_scan_uses_last_fetched_rows(monkeypatch) -> None:
    resources = RuntimeResources(llm_service=None, yf_fetcher=FakeFetcher())
    runner = RegistryToolRunner(FakeRegistry(), FakeExecutor(), resources)

    async def direct(callable_, *args):
        return callable_(*args)

    monkeypatch.setattr("app.core.agent_loop.runtime.asyncio.to_thread", direct)
    monkeypatch.setattr(
        "app.core.tools.tool_handlers.technical_scan",
        lambda args: {"rows": len(args["ohlcv_data"])},
    )

    async def execute_handler(name, args):
        from app.core.tools.tool_handlers import technical_scan

        return type("Result", (), {"to_dict": lambda self: technical_scan(args)})()

    runner.executor.execute_handler = execute_handler
    await runner.execute("data:fetch_stock_data", {"ticker": "HDFCBANK.NS"})

    result = await runner.execute("analysis:run_technical_scan", {})

    assert result == {"rows": 2}


@pytest.mark.asyncio
async def test_technical_scan_ignores_model_supplied_rows_when_cache_exists(monkeypatch) -> None:
    resources = RuntimeResources(llm_service=None, yf_fetcher=FakeFetcher())
    runner = RegistryToolRunner(FakeRegistry(), FakeExecutor(), resources)

    async def direct(callable_, *args):
        return callable_(*args)

    monkeypatch.setattr("app.core.agent_loop.runtime.asyncio.to_thread", direct)
    monkeypatch.setattr(
        "app.core.tools.tool_handlers.technical_scan",
        lambda args: {"rows": len(args["ohlcv_data"])},
    )

    async def execute_handler(name, args):
        from app.core.tools.tool_handlers import technical_scan

        return type("Result", (), {"to_dict": lambda self: technical_scan(args)})()

    runner.executor.execute_handler = execute_handler
    await runner.execute("data:fetch_stock_data", {"ticker": "HDFCBANK.NS"})

    result = await runner.execute(
        "analysis:run_technical_scan",
        {"ticker": "HDFCBANK.NS", "ohlcv_data": [{"close": 1.0}]},
    )

    assert result == {"rows": 2}


@pytest.mark.asyncio
async def test_fundamental_scan_uses_fetched_evidence_not_model_values(monkeypatch) -> None:
    resources = RuntimeResources(llm_service=None, yf_fetcher=FakeFetcher())
    runner = RegistryToolRunner(FakeRegistry(), FakeExecutor(), resources)

    async def direct(callable_, *args):
        return callable_(*args)

    monkeypatch.setattr("app.core.agent_loop.runtime.asyncio.to_thread", direct)

    await runner.execute("data:fetch_fundamentals", {"ticker": "HDFCBANK.NS"})
    captured: dict = {}

    async def execute_handler(name, args):
        captured.update(args["raw_data"])
        return type("Result", (), {"to_dict": lambda self: {"success": True}})()

    runner.executor.execute_handler = execute_handler
    await runner.execute(
        "analysis:run_fundamental_scan",
        {"raw_data": '{"pe_ratio":999,"ticker":"HDB"}'},
    )

    assert captured["ticker"] == "HDFCBANK.NS"
    assert captured["peRatio"] == 18.5
    assert "pe_ratio" not in captured
