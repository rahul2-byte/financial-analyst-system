import sys
import types
from typing import Any, cast

from app.core.ticker import parse_ticker

module_cache = cast(dict[str, Any], sys.modules)
module_cache.setdefault("yfinance", types.SimpleNamespace())
module_cache.setdefault(
    "pandas",
    types.SimpleNamespace(
        DataFrame=object,
        MultiIndex=object,
        Series=object,
        isna=lambda value: value is None,
        to_datetime=lambda value: value,
    ),
)
module_cache.setdefault("numpy", types.SimpleNamespace(ndarray=object))
module_cache.setdefault(
    "app.core.observability",
    types.SimpleNamespace(observe=lambda **_: lambda function: function),
)
module_cache.setdefault(
    "data.interfaces.fetcher",
    types.SimpleNamespace(IDataFetcher=object),
)
module_cache.setdefault(
    "data.schemas.market",
    types.SimpleNamespace(OHLCVData=object),
)
module_cache.setdefault(
    "data.schemas.text",
    types.SimpleNamespace(
        NewsArticle=type(
            "NewsArticle",
            (),
            {"__init__": lambda self, **values: self.__dict__.update(values)},
        )
    ),
)

from data.providers import yfinance as yfinance_provider
from data.providers.yfinance import YFinanceFetcher


def test_format_ticker_normalizes_explicit_nse_suffix() -> None:
    fetcher = YFinanceFetcher()

    assert fetcher._format_ticker("reliance.ns") == "RELIANCE.NS"


def test_format_ticker_applies_default_nse_suffix() -> None:
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


def test_fetch_news_reads_current_yfinance_content_shape(monkeypatch) -> None:
    item = {
        "content": {
            "title": "HDFC Bank quarterly update",
            "summary": "Earnings coverage",
            "pubDate": "2026-09-15T10:00:00Z",
            "provider": {"displayName": "Reuters"},
            "canonicalUrl": {"url": "https://example.test/hdfc"},
        }
    }
    monkeypatch.setattr(
        yfinance_provider.yf,
        "Ticker",
        lambda ticker: types.SimpleNamespace(news=[item]),
        raising=False,
    )

    articles = YFinanceFetcher().fetch_news("HDFCBANK", limit=10)

    assert len(articles) == 1
    assert articles[0].title == "HDFC Bank quarterly update"
    assert articles[0].url == "https://example.test/hdfc"


def test_fetch_news_drops_placeholder_items(monkeypatch) -> None:
    monkeypatch.setattr(
        yfinance_provider.yf,
        "Ticker",
        lambda ticker: types.SimpleNamespace(news=[{"content": {}}]),
        raising=False,
    )

    assert YFinanceFetcher().fetch_news("HDFCBANK", limit=10) == []
