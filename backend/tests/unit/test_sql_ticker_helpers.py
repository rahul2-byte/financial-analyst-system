import pytest

from storage.sql.client import PostgresClient


def test_canonical_equity_ticker_delegates_to_central_parser() -> None:
    assert PostgresClient._canonical_equity_ticker(" reliance.ns ") == "RELIANCE"
    assert PostgresClient._canonical_equity_ticker("TCS.BO") == "TCS"
    assert PostgresClient._canonical_equity_ticker("AAPL") == "AAPL"


def test_fundamentals_lookup_variants_use_central_order() -> None:
    assert PostgresClient._fundamentals_lookup_variants("RELIANCE.NS") == [
        "RELIANCE",
        "RELIANCE.NS",
        "RELIANCE.BO",
    ]
    assert PostgresClient._fundamentals_lookup_variants("aapl") == [
        "AAPL",
        "AAPL.NS",
        "AAPL.BO",
    ]


def test_fundamentals_lookup_variants_prioritize_requested_suffix_when_needed() -> None:
    assert PostgresClient._fundamentals_lookup_variants_for_request("HDFCBANK.BO") == [
        "HDFCBANK.BO",
        "HDFCBANK",
        "HDFCBANK.NS",
    ]

    assert PostgresClient._fundamentals_lookup_variants_for_request("HDFCBANK") == [
        "HDFCBANK",
        "HDFCBANK.NS",
        "HDFCBANK.BO",
    ]


@pytest.mark.parametrize("raw", [".", "-", "^", "="])
def test_operator_only_ticker_raises_value_error(raw: str) -> None:
    with pytest.raises(ValueError):
        PostgresClient._canonical_equity_ticker(raw)

    with pytest.raises(ValueError):
        PostgresClient._fundamentals_lookup_variants(raw)
