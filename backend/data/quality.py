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
        "INVALID_OHLC",
        "INSTRUMENT_MISMATCH",
        "NON_FINITE_VALUE",
        "STALE_DATA",
        "VENDOR_DISAGREEMENT",
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
        timestamp = record.get(
            "Date",
            record.get(
                "Datetime",
                record.get("date", record.get("datetime", record.get("timestamp"))),
            ),
        )
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
        values = [record.get(field) for field in ("open", "high", "low", "close")]
        if all(
            isinstance(value, (int, float)) and isfinite(float(value))
            for value in values
        ):
            numeric_values = [
                float(value) for value in values if isinstance(value, (int, float))
            ]
            open_value, high_value, low_value, close_value = numeric_values
            if high_value < max(open_value, close_value) or low_value > min(
                open_value, close_value
            ):
                issues.append(
                    DataQualityIssue(
                        code="INVALID_OHLC",
                        message=f"row {index} has impossible OHLC bounds",
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


def validate_market_freshness(
    *, observed_at: datetime, as_of: datetime, max_age_days: int
) -> tuple[DataQualityIssue, ...]:
    """Reject observations whose declared as-of time is too old."""
    if max_age_days < 0:
        raise ValueError("max_age_days must be non-negative")
    if observed_at.tzinfo is None or as_of.tzinfo is None:
        return (
            DataQualityIssue(
                code="INVALID_TIMEZONE",
                message="freshness timestamps must be timezone-aware",
            ),
        )
    age_days = (
        as_of.astimezone(UTC) - observed_at.astimezone(UTC)
    ).total_seconds() / 86_400
    if age_days > max_age_days:
        return (
            DataQualityIssue(
                code="STALE_DATA",
                message=f"observation is {age_days:.2f} days old; maximum is {max_age_days}",
            ),
        )
    return ()


def compare_vendor_values(
    values: dict[str, float], *, max_relative_difference: float
) -> tuple[DataQualityIssue, ...]:
    """Flag a material spread when independent vendors report one value."""
    if not 0 <= max_relative_difference < 1:
        raise ValueError("max_relative_difference must be in [0, 1)")
    finite_values = [
        float(value) for value in values.values() if isfinite(float(value))
    ]
    if len(finite_values) < 2:
        return ()
    low, high = min(finite_values), max(finite_values)
    if low <= 0 or (high - low) / low > max_relative_difference:
        return (
            DataQualityIssue(
                code="VENDOR_DISAGREEMENT",
                message="provider values exceed the permitted relative difference",
            ),
        )
    return ()
