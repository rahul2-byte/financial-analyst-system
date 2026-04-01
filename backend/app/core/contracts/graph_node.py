from __future__ import annotations

from typing import Any


REQUIRED_NODE_FIELDS: dict[str, type] = {
    "status": str,
    "reasoning": str,
    "confidence_score": (int, float),
    "next_action": str,
    "data": dict,
    "errors": list,
}


def validate_node_output_contract(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, expected_type in REQUIRED_NODE_FIELDS.items():
        if key not in payload:
            errors.append(f"missing required field '{key}'")
            continue
        if not isinstance(payload[key], expected_type):
            errors.append(f"field '{key}' has invalid type: {type(payload[key]).__name__}")

    payload_errors = payload.get("errors")
    if isinstance(payload_errors, list) and not all(
        isinstance(error, str) for error in payload_errors
    ):
        errors.append("field 'errors' must contain only strings")

    return errors


def finalize_node_output(node_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    contract_errors = validate_node_output_contract(payload)
    if not contract_errors:
        return payload

    return {
        "status": "failure",
        "reasoning": f"{node_name} produced an invalid output contract.",
        "confidence_score": float(payload.get("confidence_score", 0.0)),
        "next_action": "terminate_failure",
        "data": {},
        "errors": [
            f"{node_name}: {error}" for error in contract_errors
        ],
    }
