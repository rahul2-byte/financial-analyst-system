import pytest

from app.core.ticker import Ticker, parse_ticker


def test_parse_nse_suffix_normalizes_canonical_and_preserves_suffix() -> None:
    ticker = parse_ticker("  reliance.ns ")

    assert ticker.canonical == "RELIANCE"
    assert ticker.exchange_suffix == ".NS"


def test_parse_bse_suffix_normalizes_canonical_and_preserves_suffix() -> None:
    ticker = parse_ticker("TCS.BO")

    assert ticker.canonical == "TCS"
    assert ticker.exchange_suffix == ".BO"


def test_parse_plain_symbol_has_no_suffix() -> None:
    ticker = parse_ticker("AAPL")

    assert ticker.canonical == "AAPL"
    assert ticker.exchange_suffix is None


def test_db_lookup_variants_include_canonical_nse_and_bse() -> None:
    ticker = parse_ticker("RELIANCE.NS")

    assert ticker.db_lookup_variants == ("RELIANCE", "RELIANCE.NS", "RELIANCE.BO")


def test_cache_key_returns_canonical() -> None:
    ticker = parse_ticker("RELIANCE.NS")

    assert ticker.cache_key == "RELIANCE"


def test_provider_format_yfinance_uses_explicit_suffix() -> None:
    ticker = parse_ticker("RELIANCE.NS")

    assert ticker.provider_format_yfinance() == "RELIANCE.NS"


def test_provider_format_yfinance_applies_default_suffix() -> None:
    ticker = parse_ticker("TCS")
    assert ticker.provider_format_yfinance(default_exchange_suffix=".NS") == "TCS.NS"


@pytest.mark.parametrize("raw", ["^NSEI", "NIFTY=F", "BTC-USD"])
def test_provider_format_yfinance_preserves_provider_forms(raw: str) -> None:
    ticker = parse_ticker(raw)

    assert ticker.provider_format_yfinance(default_exchange_suffix=".NS") == raw


def test_provider_format_yfinance_appends_default_suffix_to_hyphenated_equity() -> None:
    ticker = parse_ticker("BAJAJ-AUTO")

    assert ticker.provider_format_yfinance(default_exchange_suffix=".NS") == "BAJAJ-AUTO.NS"


def test_parse_ticker_is_idempotent_for_existing_ticker() -> None:
    ticker = Ticker(canonical="AAPL")

    assert parse_ticker(ticker) is ticker


def test_str_returns_canonical() -> None:
    ticker = parse_ticker("RELIANCE.NS")

    assert str(ticker) == "RELIANCE"


def test_ticker_is_immutable() -> None:
    ticker = Ticker(canonical="AAPL")

    with pytest.raises(AttributeError):
        ticker.canonical = "MSFT"


def test_empty_ticker_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_ticker("   ")


@pytest.mark.parametrize("raw", [".", "-", "^", "=", "..."])
def test_operator_only_ticker_raises_value_error(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_ticker(raw)


@pytest.mark.parametrize("raw", ["BAD TICKER", "BAD/TICKER"])
def test_invalid_ticker_characters_raise_value_error(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_ticker(raw)


@pytest.mark.parametrize("default_suffix", [".", "", "  ", ".N/S"])
def test_invalid_default_exchange_suffix_raises_value_error(
    default_suffix: str,
) -> None:
    ticker = parse_ticker("TCS")

    with pytest.raises(ValueError):
        ticker.provider_format_yfinance(default_exchange_suffix=default_suffix)
