from __future__ import annotations

import pandas as pd


def generate_signals(features: pd.DataFrame) -> pd.DataFrame:
    """Return desired long-only weights; no portfolio state is mutated."""
    required = {"ticker", "timestamp", "ema", "close", "decision_ready"}
    missing = required - set(features.columns)
    if missing:
        raise ValueError(f"missing feature columns: {sorted(missing)}")
    result = features.copy()
    result["desired_weight"] = 0.0
    ready = result["decision_ready"] & (result["close"] > result["ema"])
    result.loc[ready, "desired_weight"] = 1.0
    result["signal_id"] = "ema-close-v1"
    return result
