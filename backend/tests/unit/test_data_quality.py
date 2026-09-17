from datetime import UTC, datetime

from data.quality import validate_market_records


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
