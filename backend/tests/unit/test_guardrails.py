import pytest
from app.core.agent_loop.tool_execution import ToolExecutor
from app.core.guardrails import validate_tool_arguments
from app.core.quota import QuotaExceeded, RequestQuota


def test_tool_arguments_reject_unknown_and_oversized_values() -> None:
    with pytest.raises(ValueError):
        validate_tool_arguments(
            "data:fetch_stock_data", {"ticker": "ABC", "shell": "rm"}
        )
    with pytest.raises(ValueError):
        validate_tool_arguments("news:fetch_news", {"ticker": "ABC", "limit": 21})


def test_tool_arguments_normalize_ticker() -> None:
    assert validate_tool_arguments("data:fetch_stock_data", {"ticker": " abc "}) == {
        "ticker": "ABC"
    }


@pytest.mark.asyncio
async def test_tool_executor_denies_unlisted_tool_without_calling_runner() -> None:
    class Runner:
        called = False

        async def execute(self, name, arguments):
            self.called = True
            return {"success": True}

    runner = Runner()
    result = await ToolExecutor(runner, {"data:fetch_stock_data"}).execute(
        "news:fetch_news", {"ticker": "ABC"}
    )
    assert result["success"] is False
    assert runner.called is False


def test_request_quota_is_shared_and_bounded(tmp_path) -> None:
    quota = RequestQuota(tmp_path / "quota.sqlite3", per_second=1)
    quota.reserve("upstox")
    with pytest.raises(QuotaExceeded):
        quota.reserve("upstox")
