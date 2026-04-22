from app.core.contracts.tool_result import ToolResult


def test_tool_result_supports_warnings_and_retry_metadata():
    result = ToolResult(
        tool_name="research:retrieve_news_evidence",
        input_parameters={"ticker": "INFY"},
        output_data={"items": []},
        warnings=["NO_RECENT_ARTICLES"],
        partial=True,
        retryable=True,
        trace_id="trace-1",
    )

    assert result.partial is True
    assert result.retryable is True
    assert result.trace_id == "trace-1"
