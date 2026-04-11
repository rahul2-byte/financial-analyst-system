from app.core.instrument_resolver import resolve_instruments


def test_resolve_alias_returns_mapped_instrument_key(monkeypatch):
    class _MockPostgresClient:
        def resolve_alias(self, alias_text: str):
            if alias_text == "HDFC BANK PVT LTD":
                return {
                    "instrument_key": "NSE_EQ|HDFCBANK",
                    "trading_symbol": "HDFCBANK",
                }
            return None

        def search_instruments_ranked(self, *args, **kwargs):
            return []

        def resolve_exact_symbol(self, *args, **kwargs):
            return None

        def resolve_underlying(self, *args, **kwargs):
            return []

    monkeypatch.setattr(
        "app.core.instrument_resolver.PostgresClient", _MockPostgresClient
    )

    result = resolve_instruments(
        "Analyze HDFC Bank Pvt Ltd", llm_candidates=["HDFC Bank Pvt Ltd"]
    )
    assert result.primary_instrument is not None
    assert result.primary_instrument.trading_symbol == "HDFCBANK"
