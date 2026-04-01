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

from typing import Dict, Any, Optional
from dataclasses import dataclass
from app.core.observability import observe


@dataclass
class ValuationResult:
    """Result of valuation analysis."""

    pe_ratio: Optional[float]
    pb_ratio: Optional[float]
    analysis: str


@dataclass
class HealthResult:
    """Result of financial health analysis."""

    debt_to_equity: Optional[float]
    analysis: str


@dataclass
class ProfitabilityResult:
    """Result of profitability analysis."""

    profit_margin: Optional[float]
    roe: Optional[float]
    analysis: str


def _evaluate_ratio(
    value: Optional[float],
    none_message: str,
    thresholds: list[tuple[float, str]],
    final_message: str = "",
) -> str:
    """Helper to evaluate a ratio against thresholds and build evaluation text."""
    messages = []

    if value is None:
        messages.append(none_message)
    else:
        for threshold, message in thresholds:
            if value < threshold:
                messages.append(message.format(value=value))
                break
        else:
            if final_message:
                messages.append(final_message.format(value=value))

    return " ".join(messages)


class FundamentalScanner:
    """
    Deterministic layer to evaluate raw financial metrics.
    No LLM math allowed. This class handles all ratio evaluations.
    """

    @staticmethod
    def evaluate_valuation(pe_ratio: Optional[float], pb_ratio: Optional[float]) -> str:
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
                f"Negative P/E ratio ({pe_ratio}) indicates the company is currently losing money."
            )
        elif pe_ratio < 15:
            eval_text.append(
                f"P/E ratio of {pe_ratio} suggests the stock may be undervalued or a value play."
            )
        elif pe_ratio < 25:
            eval_text.append(
                f"P/E ratio of {pe_ratio} indicates a fair or average valuation."
            )
        elif pe_ratio < 40:
            eval_text.append(
                f"P/E ratio of {pe_ratio} suggests the stock is priced for growth (slightly overvalued)."
            )
        else:
            eval_text.append(
                f"Extremely high P/E ratio of {pe_ratio} suggests significant overvaluation or high growth expectations."
            )

        if pb_ratio is not None:
            if pb_ratio < 1:
                eval_text.append(
                    f"P/B ratio of {pb_ratio} is excellent for value investors, trading below its book value."
                )
            elif pb_ratio > 3:
                eval_text.append(
                    f"P/B ratio of {pb_ratio} is high, indicating a premium on the company's assets."
                )

        return " ".join(eval_text)

    @staticmethod
    def evaluate_health(debt_to_equity: Optional[float]) -> str:
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
        elif debt_to_equity == 0:
            eval_text.append(
                "Excellent financial health: The company operates with zero debt."
            )
        elif debt_to_equity < 1.0:
            eval_text.append(
                f"Healthy leverage: Debt-to-Equity ratio of {debt_to_equity} shows a conservative balance sheet."
            )
        elif debt_to_equity < 2.0:
            eval_text.append(
                f"Moderate leverage: Debt-to-Equity ratio of {debt_to_equity} is standard for capital-intensive industries."
            )
        else:
            eval_text.append(
                f"High risk leverage: Debt-to-Equity ratio of {debt_to_equity} indicates heavy reliance on borrowing."
            )

        return " ".join(eval_text)

    @staticmethod
    def evaluate_profitability(
        profit_margin: Optional[float], roe: Optional[float]
    ) -> str:
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
            if pm_pct < 0:
                eval_text.append(
                    f"The company has a negative profit margin of {pm_pct:.2f}%, indicating operational losses."
                )
            elif pm_pct < 5:
                eval_text.append(
                    f"Thin profit margins ({pm_pct:.2f}%) suggest high competition or low pricing power."
                )
            elif pm_pct < 15:
                eval_text.append(
                    f"Healthy profit margins ({pm_pct:.2f}%) showing solid operational efficiency."
                )
            else:
                eval_text.append(
                    f"Excellent profit margins ({pm_pct:.2f}%) indicating a strong economic moat and pricing power."
                )

        if roe is not None:
            roe_pct = roe * 100
            if roe_pct > 15:
                eval_text.append(
                    f"Strong Return on Equity ({roe_pct:.2f}%) showing effective use of shareholder capital."
                )
            elif 0 < roe_pct < 5:
                eval_text.append(
                    f"Weak Return on Equity ({roe_pct:.2f}%), indicating poor capital utilization."
                )

        return " ".join(eval_text)

    @classmethod
    @observe(name="Logic:FundamentalScanner:Scan")
    def scan(cls, data: Dict[str, Any]) -> Dict[str, str]:
        """
        Runs the full suite of fundamental evaluations on raw data.

        Args:
            data: Dictionary containing fundamental data from yfinance

        Returns:
            Dictionary with valuation, health, and profitability analysis
        """
        pe = data.get("peRatio") or data.get("forwardPE")
        pb = data.get("priceToBook")
        debt_eq = data.get("debtToEquity")

        if debt_eq is not None and debt_eq > 10:
            debt_eq = debt_eq / 100.0

        margin = data.get("profitMargins")
        roe = data.get("returnOnEquity")

        pe_val = float(pe) if pe is not None else None
        pb_val = float(pb) if pb is not None else None
        debt_val = float(debt_eq) if debt_eq is not None else None
        margin_val = float(margin) if margin is not None else None
        roe_val = float(roe) if roe is not None else None

        return {
            "valuation_analysis": cls.evaluate_valuation(pe_val, pb_val),
            "financial_health_analysis": cls.evaluate_health(debt_val),
            "profitability_analysis": cls.evaluate_profitability(margin_val, roe_val),
            "raw_data_context": f"Company: {data.get('name', 'Unknown')}, Sector: {data.get('sector', 'Unknown')}, Market Cap: {data.get('marketCap', 'Unknown')}",
        }
