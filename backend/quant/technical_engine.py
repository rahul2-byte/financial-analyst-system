"""Deterministic, library-backed technical feature engine."""

from __future__ import annotations

from datetime import UTC
from hashlib import sha256
from typing import Any
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


def _measurement(
    name: str, category: str, value: float | None, rows: int
) -> IndicatorMeasurement:
    direction = "unavailable" if value is None else "neutral"
    state = "unavailable" if value is None else "observed"
    if name.startswith("RSI") and value is not None:
        direction = "bullish" if value >= 50 else "bearish"
        state = "overbought" if value >= 70 else "oversold" if value <= 30 else "range"
    return IndicatorMeasurement(
        indicator=name,
        category=category,
        value=value,
        unit="value",
        direction=direction,
        strength=None if value is None else min(abs(value) / 100, 1),
        state=state,
        lookback=rows,
        available=value is not None,
        evidence_id=f"technical:{name.lower()}",
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
        as_of = data.index[-1].to_pydatetime().astimezone(UTC)
        measurements: list[IndicatorMeasurement] = []
        close = data["close"].to_numpy(dtype=float)
        high = data["high"].to_numpy(dtype=float)
        low = data["low"].to_numpy(dtype=float)
        volume = data["volume"].to_numpy(dtype=float)
        measurements.extend(
            [
                _measurement("SMA_20", "trend", _last(talib.SMA(close, 20)), len(data)),
                _measurement("SMA_50", "trend", _last(talib.SMA(close, 50)), len(data)),
                _measurement(
                    "SMA_200", "trend", _last(talib.SMA(close, 200)), len(data)
                ),
                _measurement("EMA_20", "trend", _last(talib.EMA(close, 20)), len(data)),
                _measurement("EMA_50", "trend", _last(talib.EMA(close, 50)), len(data)),
                _measurement(
                    "EMA_200", "trend", _last(talib.EMA(close, 200)), len(data)
                ),
                _measurement(
                    "ADX_14", "trend", _last(talib.ADX(high, low, close, 14)), len(data)
                ),
                _measurement(
                    "RSI_14", "momentum", _last(talib.RSI(close, 14)), len(data)
                ),
                _measurement(
                    "ATR_14",
                    "volatility",
                    _last(talib.ATR(high, low, close, 14)),
                    len(data),
                ),
                _measurement(
                    "NATR_14",
                    "volatility",
                    _last(talib.NATR(high, low, close, 14)),
                    len(data),
                ),
                _measurement(
                    "OBV", "volume", _last(talib.OBV(close, volume)), len(data)
                ),
                _measurement(
                    "MFI_14",
                    "volume",
                    _last(talib.MFI(high, low, close, volume, 14)),
                    len(data),
                ),
            ]
        )
        macd, signal, hist = talib.MACD(close, 12, 26, 9)
        measurements.extend(
            [
                # The MACD line is the primary value; signal and histogram are
                # separately labelled outputs.
                _measurement("MACD_12_26_9", "momentum", _last(macd), len(data)),
                _measurement(
                    "MACD_SIGNAL_12_26_9", "momentum", _last(signal), len(data)
                ),
                _measurement("MACD_HIST_12_26_9", "momentum", _last(hist), len(data)),
            ]
        )
        bb_upper, _, bb_lower = talib.BBANDS(close, 20, 2, 2)
        measurements.extend(
            [
                _measurement(
                    "BBANDS_UPPER_20_2", "volatility", _last(bb_upper), len(data)
                ),
                _measurement(
                    "BBANDS_LOWER_20_2", "volatility", _last(bb_lower), len(data)
                ),
            ]
        )
        # Pandas TA Classic owns complementary indicators; keep its output isolated.
        # pandas-ta mutates an internal EMA seed for short input and can raise
        # instead of returning an unavailable indicator.
        kc = None
        cmf = None
        if len(data) >= 20:
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
        measurements.extend(
            [
                _measurement(
                    "KC_20",
                    "volatility",
                    _last(kc.iloc[:, 1]) if kc is not None else None,
                    len(data),
                ),
                _measurement("CMF_20", "volume", _last(cmf), len(data)),
            ]
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
                timezone=str(raw_provenance.get("timezone", "UTC")),
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
        data.index = pd.to_datetime(timestamps, utc=True)
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
