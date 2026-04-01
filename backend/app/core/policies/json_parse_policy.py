"""Shared policy for parsing JSON payloads from LLM responses."""

import json
import re
from typing import Any


def parse_json_from_llm_response(content: str | None) -> dict[str, Any] | None:
    """Parse JSON from LLM response, handling direct, fenced, and prefixed formats."""
    if not content:
        return None

    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    json_match = re.search(r"\{[^{}]*\}", content)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return None
