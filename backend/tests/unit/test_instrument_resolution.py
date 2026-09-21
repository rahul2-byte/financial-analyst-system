from app.core.instrument_resolution import resolve_instrument


def test_explicit_exchange_symbol_resolves_without_provider() -> None:
    result = resolve_instrument("price for tcs.ns")

    assert result.status == "resolved"
    assert result.ticker == "TCS.NS"


def test_ambiguous_name_requires_clarification() -> None:
    result = resolve_instrument(
        "price for Tata stock",
        lambda _: [
            {"trading_symbol": "TATAMOTORS", "short_name": "Tata Motors"},
            {"trading_symbol": "TATASTEEL", "short_name": "Tata Steel"},
        ],
    )

    assert result.status == "ambiguous"
    assert result.ticker is None
    assert len(result.candidates) == 2


def test_single_provider_symbol_resolves_to_nse() -> None:
    result = resolve_instrument(
        "price for Tata Motors",
        lambda _: [{"trading_symbol": "TATAMOTORS", "short_name": "Tata Motors"}],
    )

    assert result.status == "resolved"
    assert result.ticker == "TATAMOTORS.NS"


def test_hdfc_bank_name_resolves_to_nse() -> None:
    result = resolve_instrument(
        "Analyse the HDFC BANK stock for the last 1 year",
        lambda _: [{"trading_symbol": "HDFCBANK", "short_name": "HDFC Bank"}],
    )

    assert result.status == "resolved"
    assert result.ticker == "HDFCBANK.NS"
