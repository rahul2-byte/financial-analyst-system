from app.core.contracts.tool_result import ToolResult as CanonicalToolResult
from common.state import ToolResult as LegacyImportToolResult


def test_common_state_tool_result_resolves_to_canonical_contract():
    assert LegacyImportToolResult is CanonicalToolResult


def test_canonical_tool_result_extracts_metrics_from_nested_data():
    result = CanonicalToolResult(
        tool_name="analysis:test",
        input_parameters={"ticker": "AAPL"},
        output_data={"price": {"current": 123.45}, "ratios": ["P/E 21.5x"]},
    )

    result.auto_extract_metrics()

    assert result.extracted_metrics["price.current"] == 123.45
    assert result.extracted_metrics["ratios.0_0"] == 21.5
