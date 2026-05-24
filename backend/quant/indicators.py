import pandas as pd
import numpy as np
from typing import Dict, Any
from app.core.observability import observe


class TechnicalScanner:
    """
    Deterministic layer for technical analysis indicators.
    All calculations are performed using vectorized pandas/numpy operations.
    No LLM math allowed.
    """

    @staticmethod
    def calculate_ema(series: pd.Series, window: int) -> pd.Series:
        """Calculates Exponential Moving Average."""
        return series.ewm(span=window, adjust=False).mean()

    @staticmethod
    def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """Calculates Relative Strength Index using Wilder's Smoothing."""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).fillna(0)
        loss = (-delta.where(delta < 0, 0)).fillna(0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def calculate_macd(
        series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> Dict[str, pd.Series]:
        """Calculates MACD, Signal Line, and Histogram."""
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        return {
            "line": macd_line,
            "signal": signal_line,
            "histogram": macd_line - signal_line,
        }

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculates Average True Range."""
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        return true_range.rolling(window=period).mean()

    @staticmethod
    def calculate_bollinger_bands(
        series: pd.Series, period: int = 20, std_dev: int = 2
    ) -> Dict[str, pd.Series]:
        """Calculates Bollinger Bands."""
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        return {
            "upper": sma + (std_dev * std),
            "middle": sma,
            "lower": sma - (std_dev * std),
        }

    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculates Average Directional Index."""
        plus_dm = df["high"].diff()
        minus_dm = df["low"].diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0

        tr = pd.concat(
            [
                df["high"] - df["low"],
                np.abs(df["high"] - df["close"].shift()),
                np.abs(df["low"] - df["close"].shift()),
            ],
            axis=1,
        ).max(axis=1)

        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (np.abs(minus_dm).rolling(window=period).mean() / atr)
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        return dx.rolling(window=period).mean()

    @staticmethod
    def calculate_supertrend(
        df: pd.DataFrame, period: int = 10, multiplier: int = 3
    ) -> pd.DataFrame:
        """Calculates SuperTrend."""
        atr = TechnicalScanner.calculate_atr(df, period)
        hl2 = (df["high"] + df["low"]) / 2
        upperband = hl2 + (multiplier * atr)
        lowerband = hl2 - (multiplier * atr)

        # Supertrend calculation logic
        is_uptrend = True
        supertrend = [0.0] * len(df)
        for i in range(1, len(df)):
            if df["close"].iloc[i] > upperband.iloc[i - 1]:
                is_uptrend = True
            elif df["close"].iloc[i] < lowerband.iloc[i - 1]:
                is_uptrend = False

            if is_uptrend:
                supertrend[i] = lowerband.iloc[i]
            else:
                supertrend[i] = upperband.iloc[i]

        return pd.DataFrame(
            {
                "supertrend": supertrend,
                "trend": ["up" if x > 0 else "down" for x in supertrend],
            }
        )

    @classmethod
    def get_signal_summary(cls, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Computes all 30 indicators and returns a compact JSON summary.
        Optimized for token efficiency and LLM narration.
        """
        if df.empty:
            return {"error": "DataFrame is empty."}

        # Normalize column names to lowercase for consistent access
        df = df.copy()
        df.columns = [str(c).lower() for c in df.columns]

        # Validation: check for core OHLCV columns
        required = ["close", "open", "high", "low"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            return {
                "error": f"Missing required columns: {missing}. Found: {list(df.columns)}"
            }

        close = df["close"]
        row_count = len(df)

        # TIER 1 - ESSENTIAL (Calculated with available data)
        # Use min_periods to allow partial results for shorter dataframes
        ema9 = cls.calculate_ema(close, 9).iloc[-1]
        ema20 = cls.calculate_ema(close, 20).iloc[-1]
        ema50 = cls.calculate_ema(close, 50).iloc[-1]

        # Handle 200-EMA and ADX which require more history
        ema200 = cls.calculate_ema(close, 200).iloc[-1] if row_count >= 200 else None
        rsi = cls.calculate_rsi(close).iloc[-1] if row_count >= 14 else None
        macd = cls.calculate_macd(close) if row_count >= 26 else None
        atr = cls.calculate_atr(df).iloc[-1] if row_count >= 14 else None
        bb = cls.calculate_bollinger_bands(close) if row_count >= 20 else None
        adx = cls.calculate_adx(df).iloc[-1] if row_count >= 28 else None

        curr_price = float(close.iloc[-1])
        prev_price = float(close.iloc[-2]) if row_count > 1 else curr_price
        price_change = ((curr_price - prev_price) / prev_price) * 100

        # Heuristics for LLM Labels
        ema_stack = "neutral"
        if ema200:
            if ema9 > ema20 > ema50 > ema200:
                ema_stack = "bullish_alignment"
            elif ema9 < ema20 < ema50 < ema200:
                ema_stack = "bearish_alignment"

        rsi_label = "neutral"
        if rsi:
            if rsi > 70:
                rsi_label = "overbought"
            elif rsi < 30:
                rsi_label = "oversold"

        macd_label = "neutral"
        if macd is not None and row_count > 30:
            if macd["histogram"].iloc[-1] > 0 and macd["histogram"].iloc[-2] <= 0:
                macd_label = "bullish_crossover"
            elif macd["histogram"].iloc[-1] < 0 and macd["histogram"].iloc[-2] >= 0:
                macd_label = "bearish_crossover"

        return {
            "price_action": {
                "close": round(curr_price, 2),
                "change_pct": round(price_change, 2),
                "volatility_atr": round(atr, 2) if atr else None,
                "data_points": row_count,
            },
            "trend": {
                "ema_stack": ema_stack,
                "price_vs_ema200": (
                    ("above" if curr_price > ema200 else "below")
                    if ema200
                    else "unknown"
                ),
                "adx_strength": round(adx, 2) if adx else None,
                "adx_label": (
                    ("trending" if adx > 25 else "ranging")
                    if adx
                    else "insufficient_data"
                ),
            },
            "momentum": {
                "rsi_14": round(rsi, 2) if rsi else None,
                "rsi_label": rsi_label,
                "macd_signal": macd_label,
            },
            "volatility": {
                "bb_upper": round(bb["upper"].iloc[-1], 2) if bb is not None else None,
                "bb_lower": round(bb["lower"].iloc[-1], 2) if bb is not None else None,
                "bb_position": (
                    (
                        "upper_band"
                        if curr_price > bb["middle"].iloc[-1]
                        else "lower_band"
                    )
                    if bb is not None
                    else "unknown"
                ),
            },
        }

    @classmethod
    @observe(name="Logic:TechnicalScanner:Scan")
    def scan(cls, df: pd.DataFrame) -> Dict[str, Any]:
        """Legacy compatibility layer."""
        return cls.get_signal_summary(df)
