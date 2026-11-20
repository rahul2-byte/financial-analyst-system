from collections.abc import Callable
from typing import Any

from app.core.instrument_resolution import resolve_instrument

MASTER = [
    {"trading_symbol": "HDFCBANK", "name": "HDFC BANK LTD"},
    {"trading_symbol": "HDFCLIFE", "name": "HDFC LIFE INSURANCE COMPANY LIMITED"},
    {"trading_symbol": "HDFCAMC", "name": "HDFC ASSET MANAGEMENT COMPANY LTD"},
    {"trading_symbol": "CANBK", "name": "CANARA BANK"},
]


def _make_search(calls: list[str]) -> Callable[[str], list[dict[str, Any]]]:
    def search(term: str) -> list[dict[str, Any]]:
        calls.append(term)
        words = term.upper().split()
        return [
            i
            for i in MASTER
            if all(w in i["name"] or w in i["trading_symbol"] for w in words)
        ]

    return search


def test_filler_words_dropped_and_bank_kept() -> None:
    calls: list[str] = []
    result = resolve_instrument(
        "Can you analyse the HDFC BANk stock and tell me should I buy this or not .? "
        "I want full analysis",
        _make_search(calls),
    )
    assert calls[0] == "HDFC BANK"
    assert result.status == "resolved"
    assert result.ticker == "HDFCBANK.NS"


def test_hdfc_bank_resolves_exactly_without_clarification() -> None:
    result = resolve_instrument("HDFC BANK", lambda _: list(MASTER[:3]))
    assert result.status == "resolved"
    assert result.ticker == "HDFCBANK.NS"


def test_normalized_name_match_resolves() -> None:
    result = resolve_instrument(
        "Axis Bank",
        lambda _: [
            {"trading_symbol": "AXISBANK2", "name": "Axis Bank Ltd."},
            {"trading_symbol": "AXISGOLD", "name": "Axis Gold ETF"},
        ],
    )
    assert result.ticker == "AXISBANK2.NS"


def test_bare_hdfc_stays_ambiguous() -> None:
    result = resolve_instrument("HDFC", lambda _: list(MASTER[:3]))
    assert result.status == "ambiguous"
    assert result.ticker is None


def test_leading_bank_word_is_not_a_term() -> None:
    calls: list[str] = []
    resolve_instrument("bank stock price of TCS", _make_search(calls))
    assert calls[0] == "TCS"


def test_exact_normalized_name_wins_over_longer_name() -> None:
    result = resolve_instrument(
        "adani enterprises",
        lambda _: [
            {"trading_symbol": "ADANIENT", "name": "ADANI ENTERPRISES LIMITED"},
            {"trading_symbol": "ADANIX", "name": "ADANI ENTERPRISES X"},
        ],
    )
    assert result.ticker == "ADANIENT.NS"


BONDS = [
    {"trading_symbol": "765HDFC34", "name": "HDFC BANK 7.65% 2034 SR2"},
    {"trading_symbol": "771HDFCB33", "name": "HDFC BANK 7.71% 2033 SR1"},
]


def _bond_search(term: str) -> list[dict[str, Any]]:
    words = term.upper().split()
    pool = BONDS + list(MASTER)
    return [
        i
        for i in pool
        if all(w in i["name"] or w in i["trading_symbol"] for w in words)
    ]


def test_live_sentence_with_but_typo_resolves_hdfcbank() -> None:
    result = resolve_instrument(
        "Analyse the HDFC BANk stock for the last 1 year and tell me should I but "
        "it or not .?",
        _bond_search,
    )
    assert result.status == "resolved"
    assert result.ticker == "HDFCBANK.NS"


def test_unknown_filler_typo_still_resolves_via_name_subphrase() -> None:
    result = resolve_instrument("HDFC BANK zzz", lambda _: BONDS + list(MASTER))
    assert result.ticker == "HDFCBANK.NS"


def test_bonds_ranked_below_equity() -> None:
    from app.core.instrument_resolution import _rank_candidates

    ranked = _rank_candidates(BONDS + [MASTER[3], MASTER[0]], "HDFC")
    assert [i["trading_symbol"] for i in ranked[:2]] == ["HDFCBANK", "CANBK"]


def test_bond_query_finds_bond() -> None:
    result = resolve_instrument("765HDFC34", _bond_search)
    assert result.status == "resolved"
    assert result.ticker == "765HDFC34.NS"


def test_bare_hdfc_with_bonds_present_stays_ambiguous() -> None:
    result = resolve_instrument("HDFC", _bond_search)
    assert result.status == "ambiguous"
    assert result.candidates[0]["trading_symbol"].startswith("HDFC")


def test_bond_keyword_keeps_bonds_ranked_first() -> None:
    from app.core.instrument_resolution import _rank_candidates

    ranked = _rank_candidates(
        [MASTER[0], *BONDS], "HDFC BANK 7.65% 2034 BOND", wants_bond=True
    )
    assert ranked[0]["trading_symbol"] == "HDFCBANK"
    assert {i["trading_symbol"] for i in ranked} == {
        "HDFCBANK",
        *(b["trading_symbol"] for b in BONDS),
    }
