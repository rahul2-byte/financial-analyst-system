"""
Quant module - Financial analysis and indicators.

This module provides deterministic financial analysis:
- Fundamental analysis (valuation, health, profitability)
- Technical analysis (RSI, MACD, Bollinger Bands, Support/Resistance)
- Risk analysis (sector risk scoring)
- NLP-based sentiment scoring
- Report validation

Usage:
    from quant import FundamentalScanner, TechnicalScanner, ReportValidator

    # Fundamental analysis
    result = FundamentalScanner.scan({"peRatio": 15.5, "profitMargins": 0.2})

    # Technical analysis
    df = pd.DataFrame(ohlcv_data)
    result = TechnicalScanner.scan(df)
"""

from quant.fundamentals import FundamentalScanner
from quant.indicators import TechnicalScanner
from quant.validators import ReportValidator

__all__ = [
    "FundamentalScanner",
    "TechnicalScanner",
    "ReportValidator",
]
