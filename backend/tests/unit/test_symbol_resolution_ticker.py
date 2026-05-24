import pytest

from agents.financial.data.symbol_resolution import (
    RankedMatchPolicy,
    canonicalize_ticker,
    should_accept_ranked_symbol_match,
    ticker_variants,
)


def test_canonicalize_ticker_delegates_to_central_parser() -> None:
    assert canonicalize_ticker(" reliance.ns ") == "RELIANCE"


def test_canonicalize_ticker_preserves_empty_input_compatibility() -> None:
    assert canonicalize_ticker("") == ""


def test_ticker_variants_preserve_raw_suffixed_request_first() -> None:
    assert ticker_variants("RELIANCE.NS") == [
        "RELIANCE.NS",
        "RELIANCE",
        "RELIANCE.BO",
    ]


def test_ticker_variants_use_central_db_lookup_order_for_unsuffixed_request() -> None:
    assert ticker_variants("RELIANCE") == [
        "RELIANCE",
        "RELIANCE.NS",
        "RELIANCE.BO",
    ]


def test_ticker_variants_preserve_empty_input_compatibility() -> None:
    assert ticker_variants("") == []


@pytest.mark.parametrize("raw", [".", "-", "^", "="])
def test_operator_only_ticker_raises_value_error(raw: str) -> None:
    with pytest.raises(ValueError):
        canonicalize_ticker(raw)

    with pytest.raises(ValueError):
        ticker_variants(raw)


def test_ranked_match_accepts_symbol_outside_central_parser_grammar() -> None:
    accepted, symbol = should_accept_ranked_symbol_match(
        [{"trading_symbol": "foo/bar", "score": 1.0}],
        policy=RankedMatchPolicy(min_top_score=0.85, min_gap=0.1),
    )

    assert accepted is True
    assert symbol == "FOO/BAR"
