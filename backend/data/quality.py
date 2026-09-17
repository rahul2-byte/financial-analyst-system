"""Deterministic validation for provider market-data payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, Field


class DataQualityIssue(BaseModel):
    """A deterministic data-quality finding."""

    code: Literal[
        "MISSING_FIELD",
        "DUPLICATE_TIMESTAMP",
        "INVALID_TIMEZONE",
        "INVALID_PRICE",
        "INSTRUMENT_MISMATCH",
        "NON_FINITE_VALUE",
    ]
    message: str = Field(min_length=1)
    blocking: bool = True


def validate_market_records(
    records: list[dict[str, Any]], instrument: str, observed_at: datetime
) -> tuple[DataQualityIssue, ...]:
    """Validate normalized OHLCV records before downstream consumption."""
    issues: list[DataQualityIssue] = []
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        issues.append(
            DataQualityIssue(
                code="INVALID_TIMEZONE",
                message="observation timestamp must be timezone-aware",
            )
        )

    seen_timestamps: set[str] = set()
    required = ("open", "high", "low", "close", "volume")
    for index, record in enumerate(records):
        missing = [field for field in required if record.get(field) is None]
        if missing:
            issues.append(
                DataQualityIssue(
                    code="MISSING_FIELD", message=f"row {index} missing {missing}"
                )
            )
        timestamp = record.get("Date", record.get("Datetime", record.get("date")))
        if timestamp is not None:
            key = str(timestamp)
            if key in seen_timestamps:
                issues.append(
                    DataQualityIssue(
                        code="DUPLICATE_TIMESTAMP", message=f"duplicate timestamp {key}"
                    )
                )
            seen_timestamps.add(key)
        row_instrument = record.get("ticker")
        if row_instrument is not None and str(row_instrument) != instrument:
            issues.append(
                DataQualityIssue(
                    code="INSTRUMENT_MISMATCH",
                    message=f"row instrument {row_instrument!r} != {instrument!r}",
                )
            )
        for field in ("open", "high", "low", "close"):
            value = record.get(field)
            if isinstance(value, (int, float)):
                if not isfinite(float(value)):
                    issues.append(
                        DataQualityIssue(
                            code="NON_FINITE_VALUE",
                            message=f"row {index} has non-finite {field}",
                        )
                    )
                elif value <= 0:
                    issues.append(
                        DataQualityIssue(
                            code="INVALID_PRICE",
                            message=f"row {index} has non-positive {field}",
                        )
                    )
        volume = record.get("volume")
        if isinstance(volume, (int, float)) and not isfinite(float(volume)):
            issues.append(
                DataQualityIssue(
                    code="NON_FINITE_VALUE",
                    message=f"row {index} has non-finite volume",
                )
            )
    return tuple(issues)


def utc_now() -> datetime:
    """Return a timezone-aware ingestion timestamp."""
    return datetime.now(UTC)
