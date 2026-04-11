from app.core.policies.json_parse_policy import parse_json_from_llm_response


def test_parse_json_from_markdown_code_fence():
    content = (
        '```json\n{"intent_type":"greeting","response_mode":"direct_response"}\n```'
    )
    parsed = parse_json_from_llm_response(content)
    assert parsed is not None
    assert parsed["intent_type"] == "greeting"


def test_parse_json_from_prefixed_text():
    content = (
        'Here is the plan: {"intent_type":"greeting","response_mode":"direct_response"}'
    )
    parsed = parse_json_from_llm_response(content)
    assert parsed is not None
    assert parsed["response_mode"] == "direct_response"


def test_parse_json_returns_none_for_invalid_input():
    assert parse_json_from_llm_response("not json") is None


def test_parse_json_from_fenced_json_with_line_comments():
    content = """```json
{
  "ticker": null,
  "candidates": [
    "HDFC",
    "HDFCBOM", // NSE format mention
    "HDFC.NS" // alt format
  ]
}
```"""

    parsed = parse_json_from_llm_response(content)

    assert parsed is not None
    assert parsed["ticker"] is None
    assert parsed["candidates"] == ["HDFC", "HDFCBOM", "HDFC.NS"]
