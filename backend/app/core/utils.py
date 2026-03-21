import re
import json
from typing import Any, Dict, Optional


def clean_json_string(text: str) -> str:
    """
    Extracts the first JSON-like structure from a string and performs basic cleanup.
    """
    if not text:
        return ""

    # 1. Try to find content between ```json and ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
    else:
        # 2. Try to find the first '{' and the last '}'
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = text[start_idx : end_idx + 1].strip()
        else:
            cleaned = text.strip()

    # 3. Basic "Repair" for common LLM JSON errors
    # Remove trailing commas before closing braces/brackets
    cleaned = re.sub(r",\s*(\}|\])", r"\1", cleaned)

    # Ensure boolean values are lowercase (if they were capitalized)
    cleaned = re.sub(r":\s*True\b", ": true", cleaned)
    cleaned = re.sub(r":\s*False\b", ": false", cleaned)
    cleaned = re.sub(r":\s*None\b", ": null", cleaned)

    return cleaned


def safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Safely cleans and parses a JSON string.
    """
    cleaned = clean_json_string(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None
