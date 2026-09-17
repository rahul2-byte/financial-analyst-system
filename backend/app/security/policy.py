from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

_SECRET_KEYS = {"api_key", "token", "authorization", "password", "secret"}


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
    """Return a log-safe copy of mappings and sequences."""
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if (
                key_text.lower() in _SECRET_KEYS
                and isinstance(item, str)
                and item.lower().startswith("bearer ")
            ):
                redacted[key_text] = "Bearer [REDACTED]"
            elif key_text.lower() in _SECRET_KEYS:
                redacted[key_text] = "[REDACTED]"
            else:
                redacted[key_text] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if isinstance(value, str):
        return re.sub(r"Bearer\s+\S+", "Bearer [REDACTED]", value, flags=re.IGNORECASE)
    return value
