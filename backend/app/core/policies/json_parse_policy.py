"""Shared policy for parsing JSON payloads from LLM responses."""

import json
import logging
import re
from typing import Any

_json_repair: Any
try:
    import json_repair as _json_repair
except ImportError:
    _json_repair = None

json_repair: Any = _json_repair

logger = logging.getLogger(__name__)


class JSONParsingError(Exception):
    """Exception raised when all JSON parsing attempts fail."""



def _extract_json_substring(text: str) -> str:
    """Strip markdown fences, leading/trailing text to extract JSON substring."""
    text = text.strip()

    # 1. Try to find a markdown code block containing JSON
    json_match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", text, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()

    # 2. Try to find the outermost curly braces or brackets
    # Note: this simple regex handles outermost {} or [], but json_repair
    # usually handles surrounding garbage text natively. We extract it to be safe for stdlib.
    json_match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()

    return text


def parse_json_from_llm_response(
    content: str | None,
) -> dict[str, Any] | list[Any] | None:
    """
    Parse JSON from LLM response using a robust, multi-layered approach.

    Flow:
    1. Pre-processor (strip markdown fences)
    2. stdlib json.loads (fast path)
    3. json_repair (primary repair layer)
    """
    if not content:
        return None

    # Step 1: Pre-processor
    extracted_text = _extract_json_substring(content)

    if not extracted_text:
        return None

    # Step 2: stdlib json.loads (Attempt #1)
    try:
        return json.loads(extracted_text)
    except json.JSONDecodeError:
        pass

    # Often standard json.loads fails on unescaped control characters (like literal \n)
    try:
        return json.loads(extracted_text, strict=False)
    except json.JSONDecodeError:
        pass

    # Clean backslash-newlines which break strict=False
    cleaned_text = re.sub(r"\\\n", "\n", extracted_text)
    try:
        return json.loads(cleaned_text, strict=False)
    except json.JSONDecodeError:
        pass

    # Step 3: json_repair (Attempt #2)
    if json_repair is not None:
        try:
            repaired = json_repair.repair_json(content, return_objects=True)
            # json_repair returns the parsed object if return_objects=True
            if isinstance(repaired, (dict, list)):
                return repaired
            elif isinstance(repaired, str) and repaired:
                # If it returned a string representation of JSON, load it
                return json.loads(repaired)
        except Exception as e:  # noqa: BLE001 - parser fallback boundary
            logger.debug(f"json_repair failed: {e}")

    # If all local parsing attempts fail, return None.
    # Upstream orchestrator handles:
    # - LLM Re-prompt (Attempt #4)
    # - Structured Output Fallback / Error
    return None
