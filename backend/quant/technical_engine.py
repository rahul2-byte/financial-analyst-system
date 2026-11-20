"""Deterministic, library-backed technical feature engine."""

from __future__ import annotations

from hashlib import sha256
from typing import Any, Literal
from uuid import uuid4

import numpy as np
import pandas as pd
import pandas_ta_classic as pta
import talib
from quant.technical_models import (
    EvidenceProvenance,
    IndicatorMeasurement,
    TechnicalSnapshot,
)
from quant.technical_registry import CORE_REGISTRY


def _last(series: pd.Series | np.ndarray | None) -> float | None:
    if series is None or len(series) == 0:
        return None
    value = series.iloc[-1] if isinstance(series, pd.Series) else series[-1]
    return float(value) if np.isfinite(value) else None


_MAX_BAD_ROW_FRACTION = 0.02
_IST = "Asia/Kolkata"
_Direction = Literal["bullish", "bearish", "neutral", "unavailable"]


def _clip(value: float) -> float:
    return float(min(max(value, 0.0), 1.0))


def _sign_direction(value: float) -> _Direction:
    return "bullish" if value > 0 else "bearish" if value < 0 else "neutral"


def _bands(
    value: float, low: float, high: float, centre: float, scale: float
) -> tuple[_Direction, float, str]:
    """Oscillator read: direction vs ``centre``, strength = distance/scale."""
    state = "overbought" if value >= high else "oversold" if value <= low else "range"
    direction: _Direction = (
        "bullish" if value > centre else "bearish" if value < centre else "neutral"
    )
    return direction, _clip(abs(value - centre) / scale), state


def _measurement(
    name: str,
    category: str,
    value: float | None,
    rows: int,
    *,
    direction: _Direction = "neutral",
    strength: float | None = None,
    state: str = "observed",
) -> IndicatorMeasurement:
    """Build a measurement. Without a sensible direction/strength they stay
    neutral/None rather than carrying a fabricated number."""
    if value is None:
        direction, strength, state = "unavailable", None, "unavailable"
    return IndicatorMeasurement(
        indicator=name,
        category=category,
        value=value,
        unit="value",
        direction=direction,
        strength=strength,
        state=state,
        lookback=rows,
        available=value is not None,
        evidence_id=f"technical:{name.lower()}",
    )


def _ma_measurement(
    name: str, value: float | None, price: float, atr: float | None, rows: int
) -> IndicatorMeasurement:
    """Price vs moving average; strength is the gap in units of 3 ATR."""
    if value is None:
        return _measurement(name, "trend", None, rows)
    strength = (
        None if atr is None or atr <= 0 else _clip(abs(price - value) / (3 * atr))
    )
    return _measurement(
        name,
        "trend",
        value,
        rows,
        direction=_sign_direction(price - value),
        strength=strength,
        state="price_above" if price > value else "price_below",
    )


def _osc(
    name: str,
    category: str,
    value: float | None,
    rows: int,
    *,
    low: float,
    high: float,
    centre: float,
    scale: float,
) -> IndicatorMeasurement:
    if value is None:
        return _measurement(name, category, None, rows)
    direction, strength, state = _bands(value, low, high, centre, scale)
    return _measurement(
        name, category, value, rows, direction=direction, strength=strength, state=state
    )


class TechnicalEngine:
    """Compute the enabled registry using TA-Lib and Pandas TA Classic."""

    def analyze(
        self,
        frame: pd.DataFrame,
        *,
        ticker: str,
        interval: str = "1d",
        provenance: dict[str, Any] | None = None,
    ) -> TechnicalSnapshot:
        data, dropped_rows = self._validate(frame)
        # The index is Asia/Kolkata-aware; floor to microseconds so datetime
        # conversion does not warn about discarded nanoseconds.
        as_of = data.index[-1].floor("us").to_pydatetime()
        n = len(data)
        close = data["close"].to_numpy(dtype=float)
        high = data["high"].to_numpy(dtype=float)
        low = data["low"].to_numpy(dtype=float)
        volume = data["volume"].to_numpy(dtype=float)
        price = float(close[-1])
        atr = _last(talib.ATR(high, low, close, 14))
        measurements: list[IndicatorMeasurement] = []
        for kind, fn in (("SMA", talib.SMA), ("EMA", talib.EMA)):
            for period in (20, 50, 200):
                measurements.append(
                    _ma_measurement(
                        f"{kind}_{period}", _last(fn(close, period)), price, atr, n
                    )
                )
        adx = _last(talib.ADX(high, low, close, 14))
        plus_di = _last(talib.PLUS_DI(high, low, close, 14))
        minus_di = _last(talib.MINUS_DI(high, low, close, 14))
        if adx is None:
            measurements.append(_measurement("ADX_14", "trend", None, n))
        else:
            # ADX measures trend strength, not direction: direction is taken
            # from +DI/-DI only when ADX >= 25 (a trend exists).
            trending = adx >= 25
            direction: _Direction = "neutral"
            if trending and plus_di is not None and minus_di is not None:
                direction = _sign_direction(plus_di - minus_di)
            measurements.append(
                _measurement(
                    "ADX_14",
                    "trend",
                    adx,
                    n,
                    direction=direction,
                    strength=_clip(adx / 50),
                    state="trending" if trending else "weak_trend",
                )
            )
        aroon = _last(talib.AROONOSC(high, low, 14))
        measurements.append(
            _measurement(
                "AROON_14",
                "trend",
                aroon,
                n,
                direction=_sign_direction(aroon) if aroon is not None else "neutral",
                strength=None if aroon is None else _clip(abs(aroon) / 100),
                state="observed"
                if aroon is None
                else ("uptrend" if aroon > 0 else "downtrend" if aroon < 0 else "flat"),
            )
        )
        measurements.append(
            _osc(
                "RSI_14",
                "momentum",
                _last(talib.RSI(close, 14)),
                n,
                low=30,
                high=70,
                centre=50,
                scale=50,
            )
        )
        macd, signal, hist = talib.MACD(close, 12, 26, 9)
        macd_v, signal_v, hist_v = _last(macd), _last(signal), _last(hist)
        measurements.append(
            _measurement(
                "MACD_12_26_9",
                "momentum",
                macd_v,
                n,
                direction=_sign_direction(macd_v) if macd_v is not None else "neutral",
                state="above_zero"
                if macd_v is not None and macd_v > 0
                else "below_zero",
            )
        )
        measurements.append(
            _measurement("MACD_SIGNAL_12_26_9", "momentum", signal_v, n)
        )
        measurements.append(
            _measurement(
                "MACD_HIST_12_26_9",
                "momentum",
                hist_v,
                n,
                direction=_sign_direction(hist_v) if hist_v is not None else "neutral",
                # Histogram in ATR units (1 ATR = full strength).
                strength=None
                if hist_v is None or atr is None or atr <= 0
                else _clip(abs(hist_v) / atr),
                state="observed"
                if hist_v is None
                else "macd_above_signal"
                if hist_v > 0
                else "macd_below_signal",
            )
        )
        slowk, _slowd = talib.STOCH(
            high, low, close, 14, 3, talib.MA_Type.SMA, 3, talib.MA_Type.SMA
        )
        measurements.append(
            _osc(
                "STOCH_14_3_3",
                "momentum",
                _last(slowk),
                n,
                low=20,
                high=80,
                centre=50,
                scale=50,
            )
        )
        measurements.append(
            _osc(
                "CCI_20",
                "momentum",
                _last(talib.CCI(high, low, close, 20)),
                n,
                low=-100,
                high=100,
                centre=0,
                scale=200,
            )
        )
        measurements.append(
            _osc(
                "WILLR_14",
                "momentum",
                _last(talib.WILLR(high, low, close, 14)),
                n,
                low=-80,
                high=-20,
                centre=-50,
                scale=50,
            )
        )
        roc = _last(talib.ROC(close, 10))
        measurements.append(
            _measurement(
                "ROC_10",
                "momentum",
                roc,
                n,
                direction=_sign_direction(roc) if roc is not None else "neutral",
            )
        )
        measurements.extend(
            [
                _measurement("ATR_14", "volatility", atr, n),
                _measurement(
                    "NATR_14", "volatility", _last(talib.NATR(high, low, close, 14)), n
                ),
            ]
        )
        bb_upper, _, bb_lower = talib.BBANDS(close, 20, 2, 2)
        upper_v, lower_v = _last(bb_upper), _last(bb_lower)
        measurements.append(_measurement("BBANDS_UPPER_20_2", "volatility", upper_v, n))
        measurements.append(_measurement("BBANDS_LOWER_20_2", "volatility", lower_v, n))
        pct_b = (
            (price - lower_v) / (upper_v - lower_v)
            if upper_v is not None and lower_v is not None and upper_v > lower_v
            else None
        )
        measurements.append(
            _measurement(
                "BBANDS_PCT_B_20_2",
                "volatility",
                pct_b,
                n,
                direction="neutral" if pct_b is None else _sign_direction(pct_b - 0.5),
                strength=None if pct_b is None else _clip(abs(pct_b - 0.5) * 2),
                state="observed"
                if pct_b is None
                else "above_upper"
                if pct_b > 1
                else "below_lower"
                if pct_b < 0
                else "within_bands",
            )
        )
        measurements.extend(
            [
                _measurement("OBV", "volume", _last(talib.OBV(close, volume)), n),
            ]
        )
        measurements.append(
            _osc(
                "MFI_14",
                "volume",
                _last(talib.MFI(high, low, close, volume, 14)),
                n,
                low=20,
                high=80,
                centre=50,
                scale=50,
            )
        )
        # Pandas TA Classic owns complementary indicators; keep its output isolated.
        # pandas-ta mutates an internal EMA seed for short input and can raise
        # instead of returning an unavailable indicator.
        kc = None
        cmf = None
        if n >= 20:
            try:
                kc = pta.kc(data["high"], data["low"], data["close"], length=20)
                cmf = pta.cmf(
                    data["high"],
                    data["low"],
                    data["close"],
                    data["volume"],
                    length=20,
                )
            except (IndexError, ValueError):
                # Optional indicators are unavailable when pandas-ta rejects
                # a provider's short or irregular series.
                pass
        measurements.append(
            _measurement(
                "KC_20",
                "volatility",
                _last(kc.iloc[:, 1]) if kc is not None else None,
                n,
            )
        )
        cmf_v = _last(cmf)
        measurements.append(
            _measurement(
                "CMF_20",
                "volume",
                cmf_v,
                n,
                direction=_sign_direction(cmf_v) if cmf_v is not None else "neutral",
                strength=None if cmf_v is None else _clip(abs(cmf_v)),
            )
        )
        # DQ-39: 52-week range (daily bars only) and relative volume.
        daily = interval == "1d"
        high_52w = float(np.max(high[-252:])) if daily and n >= 252 else None
        low_52w = float(np.min(low[-252:])) if daily and n >= 252 else None
        measurements.append(_measurement("HIGH_52W", "range", high_52w, n))
        measurements.append(_measurement("LOW_52W", "range", low_52w, n))
        rel_volume = None
        if n >= 21:
            baseline = float(np.mean(volume[-21:-1]))
            rel_volume = float(volume[-1] / baseline) if baseline > 0 else None
        measurements.append(
            _measurement(
                "REL_VOLUME_20",
                "volume",
                rel_volume,
                n,
                state="observed"
                if rel_volume is None
                else "elevated"
                if rel_volume >= 1.5
                else "normal",
            )
        )
        raw_provenance = provenance or {}
        source = str(raw_provenance.get("source", "unknown"))
        snapshot_hash = raw_provenance.get("snapshot_hash")
        return TechnicalSnapshot(
            analysis_id=uuid4().hex,
            ticker=ticker,
            as_of=as_of,
            interval=interval,
            row_count=len(data),
            status="ok" if len(data) >= 200 else "partial",
            measurements=measurements,
            warnings=[]
            if len(data) >= 200
            else ["less than 200 bars; long lookback indicators unavailable"],
            provenance=EvidenceProvenance(
                source=source,
                snapshot_hash=str(snapshot_hash) if snapshot_hash else None,
                adjustment=str(raw_provenance.get("adjustment", "unknown")),
                timezone=str(raw_provenance.get("timezone", _IST)),
                as_of=as_of,
            ),
            metadata={
                "dropped_rows": dropped_rows,
                "registry_size": len(CORE_REGISTRY),
                "config_hash": sha256(repr(CORE_REGISTRY).encode()).hexdigest(),
            },
        )

    @staticmethod
    def _validate(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
        required = ("open", "high", "low", "close", "volume")
        columns = {str(column).lower(): column for column in frame.columns}
        missing = [column for column in required if column not in columns]
        if missing:
            raise ValueError(f"missing OHLCV columns: {missing}")
        data = frame.loc[:, [columns[column] for column in required]].copy()
        data.columns = list(required)
        timestamp_column = next(
            (
                columns[name]
                for name in ("timestamp", "date", "datetime")
                if name in columns
            ),
            None,
        )
        timestamps = (
            frame[timestamp_column] if timestamp_column is not None else frame.index
        )
        try:
            parsed = pd.DatetimeIndex(pd.to_datetime(timestamps))
        except (ValueError, TypeError):
            parsed = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True))
        # Naive timestamps are exchange-local (NSE/BSE), not host-local or UTC.
        data.index = (
            parsed.tz_localize(_IST) if parsed.tz is None else parsed.tz_convert(_IST)
        )
        data = data.sort_index()
        total_rows = len(data)
        if total_rows == 0:
            raise ValueError("OHLCV data must be non-empty and finite")
        values = data.to_numpy(dtype=float)
        finite = np.isfinite(values).all(axis=1)
        # Comparisons below are only meaningful for finite rows.
        safe = data.where(pd.Series(finite, index=data.index), 1.0)
        ohlc = safe[["open", "high", "low", "close"]]
        positive = (ohlc > 0).all(axis=1).to_numpy()
        body_max = safe[["open", "close"]].max(axis=1)
        body_min = safe[["open", "close"]].min(axis=1)
        consistent = ((safe["high"] >= body_max) & (safe["low"] <= body_min)).to_numpy()
        good = finite & positive & consistent
        dropped = int((~good).sum())
        if dropped / total_rows > _MAX_BAD_ROW_FRACTION:
            raise ValueError(
                f"too many invalid OHLCV rows: {dropped} of {total_rows} "
                f"(limit {_MAX_BAD_ROW_FRACTION:.0%})"
            )
        data = data.loc[good]
        if data.empty:
            raise ValueError("OHLCV data must be non-empty and finite")
        return data, dropped
