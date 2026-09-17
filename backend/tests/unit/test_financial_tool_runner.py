from __future__ import annotations

import pytest
from app.core.agent_loop import FinancialToolRunner
from app.core.resources import RuntimeResources


class FakeFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def fetch_stock_price(self, ticker: str, period: str, interval: str) -> dict:
        self.calls.append(("price", ticker, period, interval))
        return {
            "ticker": ticker,
            "period": period,
            "interval": interval,
            "data": [{"Close": 10}, {"Close": 12}],
        }

    def fetch_company_fundamentals(self, ticker: str) -> dict:
        self.calls.append(("fundamentals", ticker))
        return {"ticker": ticker, "peRatio": 12}

    def fetch_news(self, ticker: str, limit: int) -> list[dict]:
        self.calls.append(("news", ticker, limit))
        return [{"title": "headline"}]


def runner() -> tuple[FinancialToolRunner, FakeFetcher]:
    fetcher = FakeFetcher()
    return FinancialToolRunner(
        RuntimeResources(llm_service=object(), yf_fetcher=fetcher)
    ), fetcher


def test_definitions_are_the_current_finite_tool_surface() -> None:
    tool_runner, _ = runner()
    names = {item["function"]["name"] for item in tool_runner.definitions()}
    assert names == {
        "data:fetch_stock_data",
        "data:fetch_fundamentals",
        "news:fetch_news",
        "analysis:run_fundamental_scan",
        "analysis:run_technical_scan",
        "interaction:ask_user",
    }


@pytest.mark.asyncio
async def test_stock_data_returns_summary_and_caches_for_analysis() -> None:
    tool_runner, fetcher = runner()
    result = await tool_runner.execute("data:fetch_stock_data", {"ticker": "ABC"})
    assert result["success"] is True
    assert result["data"]["period_return_pct"] == 20.0
    await tool_runner.execute("analysis:run_technical_scan", {"ticker": "ABC"})
    assert [call[0] for call in fetcher.calls] == ["price"]


@pytest.mark.asyncio
async def test_unknown_tool_and_missing_ticker_fail_closed() -> None:
    tool_runner, _ = runner()
    unknown = await tool_runner.execute("unknown:tool", {})
    missing = await tool_runner.execute("analysis:run_technical_scan", {})
    assert unknown == {"success": False, "error": "Unknown tool: unknown:tool"}
    assert missing["success"] is False
