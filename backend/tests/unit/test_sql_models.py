def test_instrument_alias_model_exists():
    from storage.sql.models import InstrumentAlias

    alias = InstrumentAlias(
        alias_text="HDFC Bank Pvt Ltd", instrument_key="NSE_EQ|HDFCBANK"
    )
    assert alias.alias_text == "HDFC Bank Pvt Ltd"
