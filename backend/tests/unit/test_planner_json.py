"""Tests for planner JSON parsing."""

from app.core.policies.json_parse_policy import (
    parse_json_from_llm_response as _parse_json_from_response,
)


class TestParseJsonFromResponse:
    """Test JSON parsing from LLM responses."""

    def test_parse_direct_json(self):
        """Should parse direct JSON string."""
        json_str = '{"intent_type": "greeting", "response_mode": "direct_response"}'
        result = _parse_json_from_response(json_str)

        assert result is not None
        assert result["intent_type"] == "greeting"

    def test_parse_json_in_markdown(self):
        """Should parse JSON in markdown code blocks."""
        content = '```json\n{"intent_type": "greeting", "response_mode": "direct_response"}\n```'
        result = _parse_json_from_response(content)

        assert result is not None
        assert result["intent_type"] == "greeting"

    def test_parse_json_with_text_prefix(self):
        """Should parse JSON with text prefix."""
        content = 'Here is the plan: {"intent_type": "greeting", "response_mode": "direct_response"}'
        result = _parse_json_from_response(content)

        assert result is not None

    def test_parse_invalid_json_returns_none(self):
        """Should return None for invalid JSON."""
        result = _parse_json_from_response("not json at all")

        assert result is None

    def test_parse_empty_string_returns_none(self):
        """Should return None for empty string."""
        result = _parse_json_from_response("")

        assert result is None

    def test_parse_none_returns_none(self):
        """Should return None for None input."""
        result = _parse_json_from_response(None)

        assert result is None
