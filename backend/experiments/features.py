from __future__ import annotations

import hashlib
import json

import pandas as pd
from experiments.datasets import MarketDataset


def infer_bar_interval(timestamps: pd.Series) -> pd.Timedelta:
    """Median positive gap between unique timestamps (1 day if undeterminable)."""
    unique = pd.Series(sorted(timestamps.unique()))
    gaps = unique.diff().dropna()
    gaps = gaps[gaps > pd.Timedelta(0)]
    return pd.Timedelta(days=1) if gaps.empty else pd.Timedelta(gaps.median())


def generate_features(
    dataset: MarketDataset,
    *,
    ema_window: int = 10,
    bar_interval: pd.Timedelta | None = None,
) -> pd.DataFrame:
    """Generate causal features using only bars through each decision timestamp.

    ``timestamp`` is the bar open time. A bar's features use its close, so they
    become available only at ``available_at`` = open time + bar interval.
    """
    if ema_window < 2:
        raise ValueError("ema_window must be at least 2")
    frame = pd.DataFrame(list(dataset.rows))
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values(["ticker", "timestamp"]).reset_index(drop=True)
    grouped = frame.groupby("ticker", sort=False)["close"]
    frame["ema"] = grouped.transform(
        lambda series: series.ewm(
            span=ema_window, adjust=False, min_periods=ema_window
        ).mean()
    )
    interval = bar_interval or infer_bar_interval(frame["timestamp"])
    frame["available_at"] = frame["timestamp"] + interval
    frame["decision_ready"] = frame["ema"].notna()
    frame["feature_config_hash"] = hashlib.sha256(
        json.dumps({"ema_window": ema_window}, sort_keys=True).encode()
    ).hexdigest()
    return frame


def feature_fingerprint(features: pd.DataFrame) -> str:
    columns = ["ticker", "timestamp", "ema", "available_at", "decision_ready"]
    payload = features[columns].copy()
    payload["timestamp"] = payload["timestamp"].astype(str)
    payload["available_at"] = payload["available_at"].astype(str)
    return hashlib.sha256(
        payload.to_json(orient="records", date_format="iso").encode()
    ).hexdigest()
