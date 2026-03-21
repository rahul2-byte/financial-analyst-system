from typing import Dict, Any
import pandas as pd
import numpy as np
from app.core.observability import observe


class TechnicalScanner:
    """
    Deterministic layer for technical analysis indicators.
    All calculations are performed using pandas/numpy to ensure accuracy.
    No LLM math allowed.
    """

    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculates the Relative Strength Index (RSI).
        Standard formula: RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss
        """
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).fillna(0)
        loss = (-delta.where(delta < 0, 0)).fillna(0)

        # Using Wilder's Smoothing Method (EMA-based)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def calculate_macd(
        df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> Dict[str, pd.Series]:
        """
        Calculates the Moving Average Convergence Divergence (MACD).
        MACD Line = 12-period EMA - 26-period EMA
        Signal Line = 9-period EMA of MACD Line
        MACD Histogram = MACD Line - Signal Line
        """
        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        macd_hist = macd_line - signal_line

        return {
            "macd_line": macd_line,
            "signal_line": signal_line,
            "macd_hist": macd_hist,
        }

    @staticmethod
    def calculate_bollinger_bands(
        df: pd.DataFrame, period: int = 20, std_dev: int = 2
    ) -> Dict[str, pd.Series]:
        """
        Calculates Bollinger Bands.
        Middle Band = 20-period Moving Average
        Upper Band = Middle Band + (2 * 20-period Standard Deviation)
        Lower Band = Middle Band - (2 * 20-period Standard Deviation)
        """
        middle_band = df["close"].rolling(window=period).mean()
        std = df["close"].rolling(window=period).std()
        upper_band = middle_band + (std_dev * std)
        lower_band = middle_band - (std_dev * std)

        return {
            "upper_band": upper_band,
            "middle_band": middle_band,
            "lower_band": lower_band,
        }

    @staticmethod
    def calculate_support_resistance(df: pd.DataFrame) -> Dict[str, float]:
        """
        Calculates Pivot Point-based Support and Resistance levels.
        Based on the last complete bar's High, Low, and Close.
        """
        if len(df) < 1:
            return {}

        # Use the latest complete data point
        last_row = df.iloc[-1]
        high = (
            float(last_row["high"]) if "high" in last_row else float(last_row["close"])
        )
        low = float(last_row["low"]) if "low" in last_row else float(last_row["close"])
        close = float(last_row["close"])

        pivot = (high + low + close) / 3
        r1 = (2 * pivot) - low
        s1 = (2 * pivot) - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)

        return {
            "pivot": pivot,
            "resistance_1": r1,
            "support_1": s1,
            "resistance_2": r2,
            "support_2": s2,
        }

    @classmethod
    @observe(name="Logic:TechnicalScanner:Scan")
    def scan(cls, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Runs a full technical scan on the provided DataFrame.
        Returns the latest values for RSI, MACD, Bollinger Bands, and S/R levels.
        """
        if df.empty:
            return {"status": "error", "message": "DataFrame is empty"}

        # Ensure required columns exist
        required_cols = ["close"]
        if not all(col in df.columns for col in required_cols):
            return {
                "status": "error",
                "message": f"Missing required columns: {required_cols}",
            }

        rsi = cls.calculate_rsi(df)
        macd = cls.calculate_macd(df)
        bb = cls.calculate_bollinger_bands(df)
        sr = cls.calculate_support_resistance(df)

        # Get the latest values
        latest_idx = df.index[-1]

        return {
            "status": "success",
            "data": {
                "rsi": float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else None,
                "macd": {
                    "line": (
                        float(macd["macd_line"].iloc[-1])
                        if not np.isnan(macd["macd_line"].iloc[-1])
                        else None
                    ),
                    "signal": (
                        float(macd["signal_line"].iloc[-1])
                        if not np.isnan(macd["signal_line"].iloc[-1])
                        else None
                    ),
                    "histogram": (
                        float(macd["macd_hist"].iloc[-1])
                        if not np.isnan(macd["macd_hist"].iloc[-1])
                        else None
                    ),
                },
                "bollinger_bands": {
                    "upper": (
                        float(bb["upper_band"].iloc[-1])
                        if not np.isnan(bb["upper_band"].iloc[-1])
                        else None
                    ),
                    "middle": (
                        float(bb["middle_band"].iloc[-1])
                        if not np.isnan(bb["middle_band"].iloc[-1])
                        else None
                    ),
                    "lower": (
                        float(bb["lower_band"].iloc[-1])
                        if not np.isnan(bb["lower_band"].iloc[-1])
                        else None
                    ),
                },
                "levels": sr,
            },
        }
