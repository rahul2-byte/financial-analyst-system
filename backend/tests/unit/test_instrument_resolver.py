from app.core.instrument_resolver import resolve_instruments


class _StubClient:
    def resolve_exact_symbol(self, symbol: str):
        symbol = symbol.upper()
        if symbol == "AAPL":
            return {
                "instrument_key": "NSE_EQ|AAPL",
                "trading_symbol": "AAPL",
                "exchange": "NSE",
                "segment": "EQ",
                "instrument_type": "equity",
                "underlying_symbol": "AAPL",
                "company_name": "Apple Inc",
                "sector": "Technology",
                "industry": "Consumer Electronics",
            }
        if symbol == "HDFCBOM":
            return {
                "instrument_key": "NSE_EQ|HDFCBOM",
                "trading_symbol": "HDFCBOM",
                "exchange": "NSE_EQ",
                "segment": "EQ",
                "instrument_type": "equity",
                "underlying_symbol": "HDFCBOM",
                "company_name": "HDFC Bank Limited",
                "sector": "Financial Services",
                "industry": "Banks",
            }
        return None

    def resolve_underlying(
        self,
        name_or_symbol: str,
        limit: int = 5,
        exchange: str | None = None,
        segment: str = "EQ",
    ):
        if name_or_symbol.lower() == "apple":
            return [
                {
                    "instrument_key": "NSE_EQ|AAPL",
                    "trading_symbol": "AAPL",
                    "exchange": "NSE",
                    "segment": "EQ",
                    "instrument_type": "equity",
                    "underlying_symbol": "AAPL",
                    "company_name": "Apple Inc",
                    "sector": "Technology",
                    "industry": "Consumer Electronics",
                }
            ]
        if name_or_symbol.lower() == "bank":
            return [
                {
                    "instrument_key": "NSE_EQ|BANK1",
                    "trading_symbol": "BANK1",
                    "exchange": "NSE",
                    "segment": "EQ",
                    "instrument_type": "equity",
                },
                {
                    "instrument_key": "NSE_EQ|BANK2",
                    "trading_symbol": "BANK2",
                    "exchange": "NSE",
                    "segment": "EQ",
                    "instrument_type": "equity",
                },
            ]
        return []

    def search_instruments_ranked(
        self,
        query: str,
        limit: int = 10,
        exchange: str | None = None,
        segment: str | None = None,
        instrument_type: str | None = None,
    ):
        normalized = query.strip().upper()
        if normalized in {"APPLE BANK", "APPLE"}:
            return [
                {
                    "instrument_key": "NSE_EQ|AAPL",
                    "trading_symbol": "AAPL",
                    "exchange": "NSE",
                    "segment": "EQ",
                    "instrument_type": "equity",
                    "company_name": "Apple Inc",
                    "score": 0.95,
                    "match_reason": "exact_company",
                },
                {
                    "instrument_key": "NSE_EQ|APLE",
                    "trading_symbol": "APLE",
                    "exchange": "NSE",
                    "segment": "EQ",
                    "instrument_type": "equity",
                    "company_name": "Apple Hospitality",
                    "score": 0.72,
                    "match_reason": "substring",
                },
            ]
        if normalized == "BANK":
            return [
                {
                    "instrument_key": "NSE_EQ|BANK1",
                    "trading_symbol": "BANK1",
                    "exchange": "NSE",
                    "segment": "EQ",
                    "instrument_type": "equity",
                    "score": 0.82,
                    "match_reason": "prefix",
                },
                {
                    "instrument_key": "NSE_EQ|BANK2",
                    "trading_symbol": "BANK2",
                    "exchange": "NSE",
                    "segment": "EQ",
                    "instrument_type": "equity",
                    "score": 0.79,
                    "match_reason": "prefix",
                },
            ]
        return []


def test_resolve_instruments_exact_symbol(monkeypatch):
    monkeypatch.setattr("app.core.instrument_resolver.PostgresClient", _StubClient)

    result = resolve_instruments(user_query="Analyze AAPL", llm_candidates=["AAPL"])

    assert result.primary_instrument is not None
    assert result.primary_instrument.trading_symbol == "AAPL"
    assert result.ambiguous_candidates == []


def test_resolve_instruments_marks_ambiguous(monkeypatch):
    monkeypatch.setattr("app.core.instrument_resolver.PostgresClient", _StubClient)

    result = resolve_instruments(user_query="Analyze bank", llm_candidates=["bank"])

    assert result.primary_instrument is None
    assert "bank" in result.ambiguous_candidates


def test_resolve_instruments_normalizes_noisy_candidate(monkeypatch):
    monkeypatch.setattr("app.core.instrument_resolver.PostgresClient", _StubClient)

    result = resolve_instruments(
        user_query="Analyze HDFC Bank",
        llm_candidates=["HDFCBOM: NSE"],
    )

    assert result.primary_instrument is not None
    assert result.primary_instrument.trading_symbol == "HDFCBOM"


def test_resolve_instruments_uses_ranked_fuzzy_results(monkeypatch):
    monkeypatch.setattr("app.core.instrument_resolver.PostgresClient", _StubClient)

    result = resolve_instruments(
        user_query="Analyze Apple Bank",
        llm_candidates=["Apple Bank"],
    )

    assert result.primary_instrument is not None
    assert result.primary_instrument.trading_symbol == "AAPL"


def test_resolve_instruments_marks_ranked_close_scores_ambiguous(monkeypatch):
    monkeypatch.setattr("app.core.instrument_resolver.PostgresClient", _StubClient)

    result = resolve_instruments(
        user_query="Analyze bank",
        llm_candidates=["bank"],
    )

    assert result.primary_instrument is None
    assert "bank" in result.ambiguous_candidates


def test_resolve_instruments_defaults_ranked_search_to_nse_eq(monkeypatch):
    captured: dict[str, str | None] = {}

    class _FilterCaptureClient(_StubClient):
        def search_instruments_ranked(
            self,
            query: str,
            limit: int = 10,
            exchange: str | None = None,
            segment: str | None = None,
            instrument_type: str | None = None,
        ):
            captured["exchange"] = exchange
            captured["segment"] = segment
            captured["instrument_type"] = instrument_type
            return []

    monkeypatch.setattr(
        "app.core.instrument_resolver.PostgresClient", _FilterCaptureClient
    )

    resolve_instruments(user_query="Analyze Unknown", llm_candidates=["Unknown Inc"])

    assert captured["exchange"] == "NSE"
    assert captured["segment"] == "EQ"
