"""
Deterministic fundamental analysis for the Financial Intelligence Platform.

This module provides:
- Valuation analysis (P/E, P/B ratios)
- Financial health evaluation (debt levels, leverage)
- Profitability analysis (margins, ROE)

All calculations are deterministic - no LLM math allowed.

Usage:
    from quant.fundamentals import FundamentalScanner

    scanner = FundamentalScanner()
    results = scanner.scan({"peRatio": 15.5, "priceToBook": 2.3, ...})
"""

import math
from typing import Any

from app.core.observability import observe


class FundamentalScanner:
    """
    Deterministic layer to evaluate raw financial metrics.
    No LLM math allowed. This class handles all ratio evaluations.
    """

    @staticmethod
    def evaluate_valuation(
        pe_ratio: float | None,
        pb_ratio: float | None,
        *,
        sector: str | None = None,
        pe_basis: str = "trailing",
    ) -> str:
        """
        Evaluates Price/Earnings and Price/Book ratios.

        Args:
            pe_ratio: Price-to-Earnings ratio
            pb_ratio: Price-to-Book ratio

        Returns:
            Human-readable valuation analysis
        """
        eval_text: list[str] = []

        if pe_ratio is None:
            eval_text.append("P/E ratio is unavailable.")
        elif pe_ratio < 0:
            eval_text.append(
                f"{pe_basis.title()} P/E is negative ({pe_ratio}), so earnings-based valuation is not interpretable."
            )
        else:
            eval_text.append(
                f"{pe_basis.title()} P/E is {pe_ratio}; no sector peer baseline was supplied for a valuation conclusion."
            )

        if pb_ratio is not None:
            context = (
                "financial-sector"
                if (sector or "").lower()
                in {"financial services", "financials", "banks"}
                else "company"
            )
            eval_text.append(f"Price-to-book for the {context} is {pb_ratio}.")

        return " ".join(eval_text)

    @staticmethod
    def evaluate_health(debt_to_equity: float | None) -> str:
        """
        Evaluates financial risk and debt levels.

        Args:
            debt_to_equity: Debt-to-Equity ratio

        Returns:
            Human-readable financial health analysis
        """
        eval_text: list[str] = []

        if debt_to_equity is None:
            eval_text.append("Debt data is unavailable.")
        else:
            eval_text.append(
                f"Debt-to-equity is {debt_to_equity}; interpretation requires a sector-specific peer baseline."
            )

        return " ".join(eval_text)

    @staticmethod
    def evaluate_profitability(profit_margin: float | None, roe: float | None) -> str:
        """
        Evaluates margins and Return on Equity.

        Args:
            profit_margin: Profit margin (decimal, e.g., 0.15 for 15%)
            roe: Return on Equity (decimal, e.g., 0.20 for 20%)

        Returns:
            Human-readable profitability analysis
        """
        eval_text: list[str] = []

        if profit_margin is not None:
            pm_pct = profit_margin * 100
            eval_text.append(
                f"Profit margin is {pm_pct:.2f}%; no sector peer baseline was supplied."
            )

        if roe is not None:
            roe_pct = roe * 100
            eval_text.append(
                f"Return on equity is {roe_pct:.2f}%; peer context is unavailable."
            )

        return " ".join(eval_text)

    @classmethod
    @observe(name="Logic:FundamentalScanner:Scan")
    def scan(cls, data: dict[str, Any]) -> dict[str, str]:
        """
        Runs the full suite of fundamental evaluations on raw data.

        Args:
            data: Dictionary containing fundamental data from yfinance

        Returns:
            Dictionary with valuation, health, and profitability analysis
        """
        pe_key = "peRatio" if data.get("peRatio") is not None else "forwardPE"
        pe = data.get(pe_key)
        pb = data.get("priceToBook")
        debt_eq = data.get("debtToEquity")

        margin = data.get("profitMargins")
        roe = data.get("returnOnEquity")

        def finite(value: Any) -> float | None:
            try:
                converted = float(value)
            except (TypeError, ValueError):
                return None
            return converted if math.isfinite(converted) else None

        pe_val = finite(pe)
        pb_val = finite(pb)
        debt_val = finite(debt_eq)
        margin_val = finite(margin)
        roe_val = finite(roe)

        return {
            "valuation_analysis": cls.evaluate_valuation(
                pe_val,
                pb_val,
                sector=str(data.get("sector") or ""),
                pe_basis="trailing" if pe_key == "peRatio" else "forward",
            ),
            "financial_health_analysis": cls.evaluate_health(debt_val),
            "profitability_analysis": cls.evaluate_profitability(margin_val, roe_val),
            "raw_data_context": f"Company: {data.get('name', 'Unknown')}, Sector: {data.get('sector', 'Unknown')}, Market Cap: {data.get('marketCap', 'Unknown')}",
        }
