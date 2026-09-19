"""
Quant module - Financial analysis and indicators.

This module provides deterministic financial analysis:
- Fundamental analysis (valuation, health, profitability)
- Technical analysis (RSI, MACD, Bollinger Bands, Support/Resistance)

Usage:
    from quant import FundamentalScanner, TechnicalEngine

    # Fundamental analysis
    result = FundamentalScanner.scan({"peRatio": 15.5, "profitMargins": 0.2})

    # Technical analysis
    df = pd.DataFrame(ohlcv_data)
    result = TechnicalEngine().analyze(df, ticker="EXAMPLE")
"""

from quant.fundamentals import FundamentalScanner
from quant.technical_engine import TechnicalEngine

__all__ = [
    "FundamentalScanner",
    "TechnicalEngine",
]
