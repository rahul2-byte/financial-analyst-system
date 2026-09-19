from __future__ import annotations

import hashlib
import json
from datetime import datetime
from math import isfinite
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DatasetError(ValueError):
    """Dataset is malformed or has been tampered with."""


class MarketDataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    source: str
    source_hash: str
    currency: str
    timezone: str
    adjustment: str
    as_of: datetime
    rows: tuple[dict[str, Any], ...] = Field(min_length=1)
    normalized_hash: str


def _canonical(rows: list[dict[str, Any]]) -> bytes:
    return (json.dumps(rows, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def create_dataset(
    root: Path,
    *,
    dataset_id: str,
    source: str,
    source_bytes: bytes,
    rows: list[dict[str, Any]],
    currency: str,
    timezone: str,
    adjustment: str,
    as_of: datetime,
) -> MarketDataset:
    if not dataset_id or not source or not currency or not timezone:
        raise DatasetError("dataset identity and metadata are required")
    if as_of.tzinfo is None:
        raise DatasetError("as_of must be timezone-aware")
    required = {"ticker", "timestamp", "open", "high", "low", "close", "volume"}
    normalized = sorted(
        (dict(row) for row in rows),
        key=lambda row: (str(row["ticker"]), str(row["timestamp"])),
    )
    seen: set[tuple[str, str]] = set()
    for row in normalized:
        if not required <= row.keys():
            raise DatasetError("market row is missing required fields")
        key = (str(row["ticker"]), str(row["timestamp"]))
        if key in seen:
            raise DatasetError("duplicate ticker timestamp")
        seen.add(key)
        try:
            values = [
                float(row[field])
                for field in ("open", "high", "low", "close", "volume")
            ]
        except (TypeError, ValueError) as exc:
            raise DatasetError("market values must be numeric") from exc
        if any(not isfinite(value) for value in values):
            raise DatasetError("market values must be finite")
        if any(value <= 0 for value in values[:4]) or values[4] < 0:
            raise DatasetError("prices must be positive and volume non-negative")
    canonical = _canonical(normalized)
    record = MarketDataset(
        dataset_id=dataset_id,
        source=source,
        source_hash=_hash(source_bytes),
        currency=currency,
        timezone=timezone,
        adjustment=adjustment,
        as_of=as_of,
        rows=tuple(normalized),
        normalized_hash=_hash(canonical),
    )
    target = root / "datasets" / f"{dataset_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        existing = target.read_bytes()
        if existing != record.model_dump_json(indent=2).encode() + b"\n":
            raise DatasetError("dataset id already exists with different content")
    else:
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(record.model_dump_json(indent=2).encode() + b"\n")
        temporary.replace(target)
    return record


def load_dataset(root: Path, dataset_id: str) -> MarketDataset:
    path = root / "datasets" / f"{dataset_id}.json"
    try:
        record = MarketDataset.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DatasetError(f"dataset unavailable: {dataset_id}") from exc
    rows = list(record.rows)
    if _hash(_canonical(rows)) != record.normalized_hash:
        raise DatasetError("dataset normalized hash mismatch")
    return record
