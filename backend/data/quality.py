"""Deterministic validation for provider market-data payloads."""

from __future__ import annotations

from collections.abc import Collection
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from math import isfinite
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)
_INTRADAY_MINUTES = {
    "1m": 1,
    "2m": 2,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60,
    "1h": 60,
    "90m": 90,
}
# Extra trading days tolerated for coarser bars, on top of the daily threshold.
_COARSE_INTERVAL_EXTRA_DAYS = {"1wk": 5, "5d": 5, "1mo": 22, "3mo": 66}


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
        "OUT_OF_ORDER_TIMESTAMP",
        "DATA_GAP",
        "PARTIAL_SESSION",
        "VENDOR_DISAGREEMENT",
    ]
    message: str = Field(min_length=1)
    blocking: bool = True


def parse_timestamp(value: Any) -> datetime | None:
    """Parse a record timestamp; naive values are interpreted as Asia/Kolkata."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed


def is_trading_day(day: date, holidays: Collection[date] = frozenset()) -> bool:
    """Weekday and not a supplied holiday.

    The repository ships no static NSE holiday list, so by default only weekends
    are excluded; pass ``holidays`` (e.g. from Upstox) for exchange closures.
    """
    return day.weekday() < 5 and day not in holidays


def trading_days_between(
    start: date, end: date, holidays: Collection[date] = frozenset()
) -> int:
    """Count trading days in the half-open range (start, end]."""
    count = 0
    day = start + timedelta(days=1)
    while day <= end:
        if is_trading_day(day, holidays):
            count += 1
        day += timedelta(days=1)
    return count


def interval_minutes(interval: str | None) -> int | None:
    """Bar length in minutes for intraday intervals, else None."""
    return _INTRADAY_MINUTES.get((interval or "").lower())


def session_minutes_between(
    start: datetime, end: datetime, holidays: Collection[date] = frozenset()
) -> float:
    """Minutes of NSE cash-session time (09:15-15:30 IST) between two instants."""
    start_ist, end_ist = start.astimezone(IST), end.astimezone(IST)
    if end_ist <= start_ist:
        return 0.0
    total = 0.0
    day = start_ist.date()
    while day <= end_ist.date():
        if is_trading_day(day, holidays):
            opened = datetime.combine(day, SESSION_OPEN, tzinfo=IST)
            closed = datetime.combine(day, SESSION_CLOSE, tzinfo=IST)
            lo, hi = max(opened, start_ist), min(closed, end_ist)
            if hi > lo:
                total += (hi - lo).total_seconds() / 60.0
        day += timedelta(days=1)
    return total


def is_partial_daily_bar(bar_time: datetime, now: datetime) -> bool:
    """True when a daily bar is dated today (IST) and the session has not closed."""
    bar_ist, now_ist = bar_time.astimezone(IST), now.astimezone(IST)
    return (
        bar_ist.date() == now_ist.date()
        and now_ist.time() < SESSION_CLOSE
        and (now_ist.weekday() < 5)
    )


def validate_market_records(
    records: list[dict[str, Any]],
    instrument: str,
    observed_at: datetime,
    *,
    interval: str | None = None,
    holidays: Collection[date] = frozenset(),
    max_gap_trading_days: int = 5,
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
    parsed_times: list[datetime] = []
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
            parsed = parse_timestamp(timestamp)
            key = parsed.astimezone(UTC).isoformat() if parsed else str(timestamp)
            if parsed is not None:
                if parsed_times and parsed < parsed_times[-1]:
                    issues.append(
                        DataQualityIssue(
                            code="OUT_OF_ORDER_TIMESTAMP",
                            message=f"row {index} timestamp {timestamp} precedes the previous row",
                        )
                    )
                parsed_times.append(parsed)
            if key in seen_timestamps:
                issues.append(
                    DataQualityIssue(
                        code="DUPLICATE_TIMESTAMP",
                        message=f"duplicate timestamp {timestamp}",
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
    issues.extend(_gap_issues(parsed_times, interval, holidays, max_gap_trading_days))
    return tuple(issues)


def _gap_issues(
    times: list[datetime],
    interval: str | None,
    holidays: Collection[date],
    max_gap_trading_days: int,
) -> list[DataQualityIssue]:
    """Report missing bars between consecutive (ordered) timestamps."""
    if len(times) < 2:
        return []
    minutes = interval_minutes(interval)
    ist_times = [value.astimezone(IST) for value in times]
    inferred_daily = interval is None and all(
        value.hour == 0 and value.minute == 0 for value in ist_times
    )
    issues: list[DataQualityIssue] = []
    for previous, current in pairwise(ist_times):
        if current <= previous:
            continue
        if minutes is not None:
            if previous.date() == current.date():
                missing = (current - previous).total_seconds() / 60 / minutes - 1
                if missing >= 2:
                    issues.append(
                        DataQualityIssue(
                            code="DATA_GAP",
                            message=f"{int(missing)} intraday bars missing before {current.isoformat()}",
                            blocking=False,
                        )
                    )
        elif interval in (None, "1d") and (interval == "1d" or inferred_daily):
            missing_days = (
                trading_days_between(previous.date(), current.date(), holidays) - 1
            )
            if missing_days > max_gap_trading_days:
                issues.append(
                    DataQualityIssue(
                        code="DATA_GAP",
                        message=f"{missing_days} trading days missing before {current.date()}",
                        blocking=False,
                    )
                )
    return issues


def utc_now() -> datetime:
    """Return a timezone-aware ingestion timestamp."""
    return datetime.now(UTC)


def validate_market_freshness(
    *,
    observed_at: datetime,
    as_of: datetime,
    max_age_days: int,
    interval: str = "1d",
    holidays: Collection[date] = frozenset(),
) -> tuple[DataQualityIssue, ...]:
    """Reject observations that are too old for their bar interval.

    Daily and coarser bars are aged in trading days (``max_age_days``, plus a
    tolerance for weekly/monthly bars). Intraday bars are aged in NSE session
    minutes against three bar lengths, so overnight gaps do not count.
    """
    if max_age_days < 0:
        raise ValueError("max_age_days must be non-negative")
    if observed_at.tzinfo is None or as_of.tzinfo is None:
        return (
            DataQualityIssue(
                code="INVALID_TIMEZONE",
                message="freshness timestamps must be timezone-aware",
            ),
        )
    minutes = interval_minutes(interval)
    if minutes is not None:
        age = session_minutes_between(observed_at, as_of, holidays)
        limit = 3.0 * minutes
        if age > limit:
            return (
                DataQualityIssue(
                    code="STALE_DATA",
                    message=f"observation is {age:.0f} session minutes old; maximum is {limit:.0f} for {interval} bars",
                ),
            )
        return ()
    limit_days = max_age_days + _COARSE_INTERVAL_EXTRA_DAYS.get(interval.lower(), 0)
    age_days = trading_days_between(
        observed_at.astimezone(IST).date(), as_of.astimezone(IST).date(), holidays
    )
    if age_days > limit_days:
        return (
            DataQualityIssue(
                code="STALE_DATA",
                message=f"observation is {age_days} trading days old; maximum is {limit_days}",
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
