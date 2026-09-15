"""Sanitize untrusted text before it reaches a terminal."""

from __future__ import annotations

import re

_ESCAPE_SEQUENCE = re.compile(r"\x1b(?:\][^\x07]*(?:\x07|\x1b\\)|\[[0-?]*[ -/]*[@-~])")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_terminal_text(value: str) -> str:
    """Remove ANSI/OSC escapes and unsafe controls while preserving whitespace."""
    return _CONTROL.sub("", _ESCAPE_SEQUENCE.sub("", value))
