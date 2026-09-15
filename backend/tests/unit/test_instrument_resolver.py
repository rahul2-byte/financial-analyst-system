from app.core.instrument_resolver import resolve_instruments


def test_resolve_instruments_accepts_nse_candidate() -> None:
    result = resolve_instruments("Analyze INFY", ["INFY"])

    assert result.primary_instrument is not None
    assert result.primary_instrument.instrument_key == "NSE_EQ:INFY"
    assert result.resolver_source == "deterministic_candidate"


def test_resolve_instruments_preserves_bse_suffix() -> None:
    result = resolve_instruments("Analyze BSE stock", ["500325.BO"])

    assert result.primary_instrument is not None
    assert result.primary_instrument.instrument_key == "BSE_EQ:500325"


def test_resolve_instruments_does_not_guess_company_names() -> None:
    result = resolve_instruments("Analyze an unknown company", ["Unknown Company"])

    assert result.primary_instrument is None
    assert result.unresolved_entities == ["Unknown Company"]
