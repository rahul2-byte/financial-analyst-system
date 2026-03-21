from typing import Dict, Any
from app.core.observability import observe


class FundamentalScanner:
    """
    Deterministic layer to evaluate raw financial metrics.
    No LLM math allowed. This class handles all ratio evaluations.
    """

    @staticmethod
    def evaluate_valuation(pe_ratio: float, pb_ratio: float) -> str:
        """Evaluates Price/Earnings and Price/Book ratios."""
        eval_text = []

        # P/E Evaluation
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

        # P/B Evaluation
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
    def evaluate_health(debt_to_equity: float, current_ratio: float = None) -> str:
        """Evaluates financial risk and debt levels."""
        eval_text = []

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
    def evaluate_profitability(profit_margin: float, roe: float) -> str:
        """Evaluates margins and Return on Equity."""
        eval_text = []

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
            elif roe_pct < 5 and roe_pct > 0:
                eval_text.append(
                    f"Weak Return on Equity ({roe_pct:.2f}%), indicating poor capital utilization."
                )

        return " ".join(eval_text)

    @classmethod
    @observe(name="Logic:FundamentalScanner:Scan")
    def scan(cls, data: Dict[str, Any]) -> Dict[str, str]:
        """Runs the full suite of fundamental evaluations on raw data."""
        pe = data.get("peRatio") or data.get("forwardPE")
        pb = data.get("priceToBook")
        debt_eq = data.get("debtToEquity")

        # Debt to equity from yfinance is sometimes expressed as a percentage (e.g., 50 means 0.5)
        # We normalize it here if it looks abnormally large
        if debt_eq and debt_eq > 10:
            debt_eq = debt_eq / 100.0

        margin = data.get("profitMargins")
        roe = data.get("returnOnEquity")

        return {
            "valuation_analysis": cls.evaluate_valuation(pe, pb),
            "financial_health_analysis": cls.evaluate_health(debt_eq),
            "profitability_analysis": cls.evaluate_profitability(margin, roe),
            "raw_data_context": f"Company: {data.get('name', 'Unknown')}, Sector: {data.get('sector', 'Unknown')}, Market Cap: {data.get('marketCap', 'Unknown')}",
        }
