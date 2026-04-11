from scripts.load_upstox_instruments import _normalize_row


def test_normalize_row_maps_core_fields() -> None:
    row = {
        "instrument_key": "NSE_EQ|RELIANCE",
        "exchange": "NSE",
        "segment": "EQ",
        "trading_symbol": "RELIANCE",
        "underlying_symbol": "RELIANCE",
        "company_name": "Reliance Industries",
        "sector": "Energy",
        "industry": "Oil & Gas",
    }

    normalized = _normalize_row(row, snapshot_id="snap-1", as_of_date=None)

    assert normalized is not None
    assert normalized["instrument_key"] == "NSE_EQ|RELIANCE"
    assert normalized["trading_symbol"] == "RELIANCE"
    assert normalized["segment"] == "EQ"
    assert normalized["instrument_type"] == "equity"
