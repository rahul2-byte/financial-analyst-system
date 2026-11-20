from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

# One pattern-based redactor shared by logging, feedback and tracing. Keys match
# by substring so access_token, x-api-key and OPENROUTER_API_KEY are all covered;
# plural ``tokens`` (usage counters) is deliberately not a secret.
_SECRET_KEY = re.compile(
    r"(?i)(api[-_]?key|apikey|authorization|cookie|passw(?:or)?d|passphrase|secret|"
    r"credential|private[-_]?key|session[-_]?id|token(?!s\b))"
)
_BEARER_VALUE = re.compile(r"(?i)\bBearer\s+[^\s,;}\"']+")
_KEYED_VALUE = re.compile(
    r"(?i)((?:api[-_]?key|apikey|token|secret|passw(?:or)?d)[\w-]*\s*[:=]\s*)"
    r"[^\s,;}\"']+"
)
_PROVIDER_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}")


class Permission(BaseModel):
    model_config = ConfigDict(frozen=True)
    subject: str
    action: str
    resource: str


class DataLicense(BaseModel):
    model_config = ConfigDict(frozen=True)
    source: str
    permitted_use: str
    expires_at: datetime | None = None
    redistribution_allowed: bool = False


def authorize(context: Permission, permission: Permission) -> bool:
    """Allow only an exact subject/action/resource match."""
    return context == permission


def license_is_valid(license: DataLicense, now: datetime | None = None) -> bool:
    """Return whether a dataset license is currently usable."""
    return license.expires_at is None or license.expires_at > (now or datetime.now(UTC))


def redact_secrets(value: Any) -> Any:
    """Return a log-safe copy of mappings, sequences and strings."""
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_KEY.search(key_text):
                redacted[key_text] = (
                    "Bearer [REDACTED]"
                    if isinstance(item, str) and item.lower().startswith("bearer ")
                    else "[REDACTED]"
                )
            else:
                redacted[key_text] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if isinstance(value, str):
        text = _BEARER_VALUE.sub("Bearer [REDACTED]", value)
        text = _KEYED_VALUE.sub(r"\1[REDACTED]", text)
        return _PROVIDER_KEY.sub("[REDACTED]", text)
    return value
