import json
from typing import Any, Dict, Optional
from app.core.policies.json_parse_policy import parse_json_from_llm_response


def clean_json_string(text: str) -> str:
    """
    Extracts the first JSON-like structure from a string and performs basic cleanup.
    """
    if not text:
        return ""

    parsed = parse_json_from_llm_response(text)
    if parsed is not None:
        return json.dumps(parsed)
    return text.strip()


def safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Safely cleans and parses a JSON string.
    """
    cleaned = clean_json_string(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None
