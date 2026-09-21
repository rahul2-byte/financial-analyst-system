"""Independent, dependency-light reference indicator calculations."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise
from statistics import fmean


def sma(values: Sequence[float], period: int) -> float:
    if period < 1 or len(values) < period:
        raise ValueError("insufficient values for SMA")
    return fmean(values[-period:])


def rsi(values: Sequence[float], period: int = 14) -> float:
    if period < 1 or len(values) <= period:
        raise ValueError("insufficient values for RSI")
    changes = [current - previous for previous, current in pairwise(values)]
    gains = [max(change, 0.0) for change in changes[-period:]]
    losses = [max(-change, 0.0) for change in changes[-period:]]
    average_gain = fmean(gains)
    average_loss = fmean(losses)
    if average_loss == 0:
        return 100.0
    return 100 - (100 / (1 + average_gain / average_loss))


def macd(values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float, float]:
    if min(fast, slow, signal) < 1 or len(values) < slow + signal:
        raise ValueError("insufficient values for MACD")

    def ema(series: Sequence[float], period: int) -> list[float]:
        multiplier = 2 / (period + 1)
        result = [fmean(series[:period])]
        for value in series[period:]:
            result.append((value - result[-1]) * multiplier + result[-1])
        return result

    fast_values = ema(values, fast)
    slow_values = ema(values, slow)
    offset = slow - fast
    line = [fast_values[index + offset] - slow_value for index, slow_value in enumerate(slow_values)]
    signal_values = ema(line, signal)
    macd_value = line[-1]
    signal_value = signal_values[-1]
    return macd_value, signal_value, macd_value - signal_value
