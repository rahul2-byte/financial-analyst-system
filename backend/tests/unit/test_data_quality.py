from datetime import UTC, datetime

from data.quality import (
    compare_vendor_values,
    validate_market_freshness,
    validate_market_records,
)


def _row(timestamp: str = "2026-01-01T00:00:00+00:00") -> dict:
    return {
        "ticker": "TEST.NS",
        "Date": timestamp,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 10,
    }


def test_market_quality_accepts_valid_records() -> None:
    issues = validate_market_records(
        [_row()], "TEST.NS", datetime(2026, 1, 1, tzinfo=UTC)
    )

    assert issues == ()


def test_market_quality_reports_duplicate_and_invalid_rows() -> None:
    invalid = _row()
    invalid["close"] = 0
    invalid.pop("volume")
    issues = validate_market_records(
        [_row(), invalid], "TEST.NS", datetime(2026, 1, 1, tzinfo=UTC)
    )

    codes = {issue.code for issue in issues}
    assert {"DUPLICATE_TIMESTAMP", "INVALID_PRICE", "MISSING_FIELD"} <= codes


def test_market_quality_reports_instrument_mismatch() -> None:
    row = _row()
    row["ticker"] = "OTHER.NS"

    issues = validate_market_records([row], "TEST.NS", datetime(2026, 1, 1, tzinfo=UTC))

    assert any(issue.code == "INSTRUMENT_MISMATCH" for issue in issues)


def test_market_quality_rejects_non_finite_values() -> None:
    row = _row()
    row["close"] = float("nan")
    row["volume"] = float("inf")

    issues = validate_market_records([row], "TEST.NS", datetime(2026, 1, 1, tzinfo=UTC))

    assert sum(issue.code == "NON_FINITE_VALUE" for issue in issues) == 2


def test_market_freshness_rejects_an_observation_older_than_its_interval() -> None:
    issues = validate_market_freshness(
        observed_at=datetime(2026, 9, 1, tzinfo=UTC),
        as_of=datetime(2026, 9, 18, tzinfo=UTC),
        max_age_days=1,
    )

    assert issues[0].code == "STALE_DATA"
    assert issues[0].blocking is True


def test_vendor_comparison_flags_material_disagreement() -> None:
    issues = compare_vendor_values(
        {"yfinance": 100.0, "other_vendor": 110.0}, max_relative_difference=0.02
    )

    assert issues[0].code == "VENDOR_DISAGREEMENT"
