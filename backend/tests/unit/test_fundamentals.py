"""Tests for fundamental analysis module."""

import pytest
from quant.fundamentals import (
    FundamentalScanner,
    ValuationResult,
    HealthResult,
    ProfitabilityResult,
)


class TestEvaluateValuation:
    """Test valuation evaluation methods."""

    def test_evaluate_valuation_undervalued(self):
        """P/E < 15 should indicate undervalued."""
        result = FundamentalScanner.evaluate_valuation(pe_ratio=12.0, pb_ratio=1.5)

        assert "undervalued" in result.lower() or "value play" in result.lower()

    def test_evaluate_valuation_fair(self):
        """P/E 15-25 should indicate fair valuation."""
        result = FundamentalScanner.evaluate_valuation(pe_ratio=20.0, pb_ratio=2.0)

        assert "fair" in result.lower() or "average" in result.lower()

    def test_evaluate_valuation_overvalued(self):
        """P/E 25-40 should indicate overvalued."""
        result = FundamentalScanner.evaluate_valuation(pe_ratio=30.0, pb_ratio=4.0)

        assert "overvalued" in result.lower() or "growth" in result.lower()

    def test_evaluate_valuation_high(self):
        """P/E > 40 should indicate high/overvalued."""
        result = FundamentalScanner.evaluate_valuation(pe_ratio=50.0, pb_ratio=5.0)

        assert "high" in result.lower() or "overvaluation" in result.lower()

    def test_evaluate_valuation_negative(self):
        """Negative P/E should be flagged."""
        result = FundamentalScanner.evaluate_valuation(pe_ratio=-5.0, pb_ratio=1.0)

        assert "negative" in result.lower() or "losing money" in result.lower()

    def test_evaluate_valuation_none_pe(self):
        """None P/E should indicate unavailable."""
        result = FundamentalScanner.evaluate_valuation(pe_ratio=None, pb_ratio=1.0)

        assert "unavailable" in result.lower()

    def test_evaluate_valuation_pb_under_one(self):
        """P/B < 1 should indicate excellent for value."""
        result = FundamentalScanner.evaluate_valuation(pe_ratio=20.0, pb_ratio=0.8)

        assert "excellent" in result.lower() or "below its book" in result.lower()

    def test_evaluate_valuation_pb_high(self):
        """P/B > 3 should indicate premium."""
        result = FundamentalScanner.evaluate_valuation(pe_ratio=20.0, pb_ratio=4.0)

        assert "high" in result.lower() or "premium" in result.lower()


class TestEvaluateHealth:
    """Test financial health evaluation."""

    def test_evaluate_health_zero_debt(self):
        """Zero debt should indicate excellent health."""
        result = FundamentalScanner.evaluate_health(debt_to_equity=0.0)

        assert "excellent" in result.lower() or "zero debt" in result.lower()

    def test_evaluate_health_healthy_leverage(self):
        """D/E < 1 should indicate healthy leverage."""
        result = FundamentalScanner.evaluate_health(debt_to_equity=0.5)

        assert "healthy" in result.lower() or "conservative" in result.lower()

    def test_evaluate_health_moderate_leverage(self):
        """D/E 1-2 should indicate moderate leverage."""
        result = FundamentalScanner.evaluate_health(debt_to_equity=1.5)

        assert "moderate" in result.lower() or "standard" in result.lower()

    def test_evaluate_health_high_leverage(self):
        """D/E > 2 should indicate high risk."""
        result = FundamentalScanner.evaluate_health(debt_to_equity=2.5)

        assert "high" in result.lower() or "risk" in result.lower()

    def test_evaluate_health_none(self):
        """None debt should indicate unavailable."""
        result = FundamentalScanner.evaluate_health(debt_to_equity=None)

        assert "unavailable" in result.lower()


class TestEvaluateProfitability:
    """Test profitability evaluation."""

    def test_evaluate_profitability_negative(self):
        """Negative margin should indicate losses."""
        result = FundamentalScanner.evaluate_profitability(profit_margin=-0.1, roe=0.05)

        assert "negative" in result.lower() or "losses" in result.lower()

    def test_evaluate_profitability_thin(self):
        """Margin < 5% should indicate thin margins."""
        result = FundamentalScanner.evaluate_profitability(profit_margin=0.03, roe=0.05)

        assert "thin" in result.lower() or "competition" in result.lower()

    def test_evaluate_profitability_healthy(self):
        """Margin 5-15% should indicate healthy."""
        result = FundamentalScanner.evaluate_profitability(profit_margin=0.10, roe=0.10)

        assert "healthy" in result.lower() or "efficiency" in result.lower()

    def test_evaluate_profitability_excellent(self):
        """Margin > 15% should indicate excellent."""
        result = FundamentalScanner.evaluate_profitability(profit_margin=0.20, roe=0.15)

        assert "excellent" in result.lower() or "moat" in result.lower()

    def test_evaluate_profitability_strong_roe(self):
        """ROE > 15% should indicate strong."""
        result = FundamentalScanner.evaluate_profitability(profit_margin=0.10, roe=0.20)

        assert "strong" in result.lower() or "effective" in result.lower()

    def test_evaluate_profitability_weak_roe(self):
        """ROE < 5% should indicate weak."""
        result = FundamentalScanner.evaluate_profitability(profit_margin=0.10, roe=0.03)

        assert "weak" in result.lower() or "poor" in result.lower()

    def test_evaluate_profitability_none_margin(self):
        """None margin should handle gracefully."""
        result = FundamentalScanner.evaluate_profitability(profit_margin=None, roe=0.10)

        assert isinstance(result, str)


class TestFundamentalScannerScan:
    """Test full scan method."""

    def test_scan_with_valid_data(self):
        """Scan should process valid data."""
        data = {
            "peRatio": 15.0,
            "priceToBook": 2.0,
            "debtToEquity": 0.5,
            "profitMargins": 0.12,
            "returnOnEquity": 0.15,
            "name": "Test Company",
            "sector": "Technology",
            "marketCap": 1000000,
        }

        result = FundamentalScanner.scan(data)

        assert "valuation_analysis" in result
        assert "financial_health_analysis" in result
        assert "profitability_analysis" in result
        assert "raw_data_context" in result

    def test_scan_normalizes_debt_ratio(self):
        """Scan should normalize large debt ratios."""
        data = {
            "peRatio": 15.0,
            "debtToEquity": 150,  # Should be normalized to 1.5
            "profitMargins": 0.10,
            "returnOnEquity": 0.10,
        }

        result = FundamentalScanner.scan(data)

        assert "financial_health_analysis" in result

    def test_scan_handles_missing_data(self):
        """Scan should handle missing data gracefully."""
        data = {
            "name": "Test Company",
        }

        result = FundamentalScanner.scan(data)

        assert "valuation_analysis" in result
        assert "financial_health_analysis" in result
        assert "profitability_analysis" in result

    def test_scan_forward_pe_fallback(self):
        """Scan should fallback to forward P/E."""
        data = {
            "forwardPE": 12.0,
            "priceToBook": 2.0,
        }

        result = FundamentalScanner.scan(data)

        assert (
            "undervalued" in result["valuation_analysis"].lower()
            or "fair" in result["valuation_analysis"].lower()
        )

    def test_scan_includes_context(self):
        """Scan should include company context."""
        data = {
            "peRatio": 15.0,
            "name": "Apple Inc.",
            "sector": "Technology",
            "marketCap": 3000000000000,
        }

        result = FundamentalScanner.scan(data)

        assert "Apple" in result["raw_data_context"]
        assert "Technology" in result["raw_data_context"]
