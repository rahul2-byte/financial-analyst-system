import sys
import types

from app.core.ticker import parse_ticker

sys.modules.setdefault("yfinance", types.SimpleNamespace())
sys.modules.setdefault(
    "pandas",
    types.SimpleNamespace(
        DataFrame=object,
        MultiIndex=object,
        Series=object,
        isna=lambda value: value is None,
        to_datetime=lambda value: value,
    ),
)
sys.modules.setdefault("numpy", types.SimpleNamespace(ndarray=object))
sys.modules.setdefault(
    "app.core.observability",
    types.SimpleNamespace(observe=lambda **_: lambda function: function),
)
sys.modules.setdefault(
    "data.interfaces.fetcher",
    types.SimpleNamespace(IDataFetcher=object),
)
sys.modules.setdefault(
    "data.schemas.market",
    types.SimpleNamespace(OHLCVData=object),
)
sys.modules.setdefault(
    "data.schemas.text",
    types.SimpleNamespace(NewsArticle=object),
)

from data.providers.yfinance import YFinanceFetcher  # noqa: E402


def test_format_ticker_normalizes_explicit_nse_suffix() -> None:
    fetcher = YFinanceFetcher()

    assert fetcher._format_ticker("reliance.ns") == "RELIANCE.NS"


def test_format_ticker_applies_legacy_default_nse_suffix() -> None:
    fetcher = YFinanceFetcher()

    assert fetcher._format_ticker("TCS") == "TCS.NS"


def test_format_ticker_accepts_parsed_ticker() -> None:
    fetcher = YFinanceFetcher()

    assert fetcher._format_ticker(parse_ticker("TCS.BO")) == "TCS.BO"


def test_format_ticker_preserves_index_symbol() -> None:
    fetcher = YFinanceFetcher()

    assert fetcher._format_ticker("^NSEI") == "^NSEI"


def test_format_ticker_preserves_futures_symbol() -> None:
    fetcher = YFinanceFetcher()

    assert fetcher._format_ticker("NIFTY=F") == "NIFTY=F"


def test_format_ticker_preserves_crypto_pair() -> None:
    fetcher = YFinanceFetcher()

    assert fetcher._format_ticker("BTC-USD") == "BTC-USD"


def test_format_ticker_appends_nse_suffix_to_hyphenated_equity() -> None:
    fetcher = YFinanceFetcher()

    assert fetcher._format_ticker("BAJAJ-AUTO") == "BAJAJ-AUTO.NS"
