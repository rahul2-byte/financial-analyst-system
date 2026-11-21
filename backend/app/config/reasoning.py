"""Parse per-purpose reasoning settings into an OpenRouter ``reasoning`` object."""

from __future__ import annotations

from typing import Any

_EFFORTS = frozenset({"minimal", "low", "medium", "high"})
_UNSET = frozenset({"", "unset", "default", "none"})


def parse_reasoning(value: str | None) -> dict[str, Any] | None:
    """Return the request ``reasoning`` object, or None to send nothing.

    ``unset`` -> None; ``off`` -> {"enabled": false}; ``minimal|low|medium|high``
    -> {"effort": ...}; ``tokens:N`` -> {"max_tokens": N}.
    """
    text = (value or "").strip().casefold()
    if text in _UNSET:
        return None
    if text == "off":
        return {"enabled": False}
    if text in _EFFORTS:
        return {"effort": text}
    if text.startswith("tokens:"):
        try:
            budget = int(text.split(":", 1)[1])
        except ValueError:
            budget = 0
        if budget > 0:
            return {"max_tokens": budget}
    raise ValueError(
        f"invalid reasoning setting {value!r}: use unset, off, minimal, low, "
        "medium, high or tokens:N"
    )
