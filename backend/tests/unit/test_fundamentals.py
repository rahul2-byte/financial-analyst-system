"""Tests for schema-aware deterministic fundamental analysis."""

import math

from quant.fundamentals import FundamentalScanner


def test_valuation_reports_observation_without_universal_verdict() -> None:
    result = FundamentalScanner.evaluate_valuation(12.0, 1.5, sector="Technology")
    assert "P/E is 12.0" in result
    assert "peer baseline" in result
    assert "undervalued" not in result


def test_negative_pe_is_not_interpreted_as_a_valuation_multiple() -> None:
    result = FundamentalScanner.evaluate_valuation(-5.0, None)
    assert "not interpretable" in result


def test_financial_sector_pb_is_described_without_industrial_debt_rule() -> None:
    result = FundamentalScanner.evaluate_valuation(
        10.0, 1.2, sector="Financial Services"
    )
    assert "financial-sector" in result


def test_health_requires_sector_peer_context() -> None:
    result = FundamentalScanner.evaluate_health(0.5)
    assert "peer baseline" in result
    assert "healthy" not in result.lower()


def test_profitability_reports_value_and_missing_context() -> None:
    result = FundamentalScanner.evaluate_profitability(0.10, 0.20)
    assert "10.00%" in result
    assert "peer context" in result


def test_scan_preserves_provider_debt_units_without_magnitude_guess() -> None:
    result = FundamentalScanner.scan({"debtToEquity": 150})
    assert "150.0" in result["financial_health_analysis"]


def test_scan_rejects_non_finite_values_as_unavailable() -> None:
    result = FundamentalScanner.scan({"peRatio": math.inf, "profitMargins": math.nan})
    assert "unavailable" in result["valuation_analysis"]
    assert (
        result["profitability_analysis"] == "Return on equity is unavailable."
        or result["profitability_analysis"] == ""
    )


def test_scan_uses_forward_pe_only_when_trailing_is_missing() -> None:
    result = FundamentalScanner.scan({"forwardPE": 12.0})
    assert "Forward P/E is 12.0" in result["valuation_analysis"]


def test_scan_keeps_company_context() -> None:
    result = FundamentalScanner.scan(
        {"name": "Apple Inc.", "sector": "Technology", "marketCap": 10}
    )
    assert "Apple" in result["raw_data_context"]
    assert "Technology" in result["raw_data_context"]
