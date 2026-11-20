from __future__ import annotations

from math import sqrt
from typing import Any

TRADING_DAYS_PER_YEAR = 252


def _equity_returns(equity: tuple[dict[str, Any], ...]) -> list[float]:
    values = [float(item["equity"]) for item in equity]
    return [
        (values[index] / values[index - 1]) - 1
        for index in range(1, len(values))
        if values[index - 1] != 0
    ]


def _summarise(
    returns: list[float],
    *,
    observations: int,
    trade_count: int,
    total_cost: float,
    stale_bars: int,
    periods_per_year: float,
    risk_free_rate: float,
) -> dict[str, Any]:
    """Metrics from per-bar returns.

    ``risk_free_rate`` is an annual rate (for INR, e.g. a T-bill yield; the
    default 0.0 means Sharpe uses raw returns). Volatility and Sharpe are
    annualised with ``periods_per_year`` (252 for daily NSE bars).
    """
    level = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        level *= 1 + value
        peak = max(peak, level)
        max_drawdown = min(max_drawdown, (level - peak) / peak)
    result: dict[str, Any] = {
        "status": "measured",
        "trade_count": trade_count,
        "cumulative_return": level - 1,
        "max_drawdown": max_drawdown,
        "observations": observations,
        "total_cost": total_cost,
        "stale_bars": stale_bars,
        "periods_per_year": periods_per_year,
        "risk_free_rate": risk_free_rate,
        "cagr": None,
        "volatility": None,
        "volatility_per_bar": None,
        "sharpe_like": None,
        "sharpe_ratio": None,
    }
    if returns and level > 0:
        result["cagr"] = level ** (periods_per_year / len(returns)) - 1
    if len(returns) >= 2:
        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
        per_bar_rf = (1 + risk_free_rate) ** (1 / periods_per_year) - 1
        result["volatility_per_bar"] = sqrt(variance)
        result["volatility"] = sqrt(variance) * sqrt(periods_per_year)
        if variance > 0:
            sharpe = (mean - per_bar_rf) / sqrt(variance) * sqrt(periods_per_year)
            result["sharpe_ratio"] = sharpe
            result["sharpe_like"] = sharpe
    return result


def _stale(equity: tuple[dict[str, Any], ...]) -> int:
    return sum(1 for item in equity if item.get("stale_tickers"))


def calculate_metrics(
    equity: tuple[dict[str, Any], ...],
    fills: tuple[Any, ...],
    *,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    risk_free_rate: float = 0.0,
) -> dict[str, Any]:
    if not equity:
        return {"status": "insufficient_data", "reason": "empty_equity"}
    return _summarise(
        _equity_returns(equity),
        observations=len(equity),
        trade_count=len(fills),
        total_cost=sum(float(fill.fee) for fill in fills),
        stale_bars=_stale(equity),
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
    )


def aggregate_window_metrics(
    windows: list[tuple[tuple[dict[str, Any], ...], tuple[Any, ...]]],
    *,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
    risk_free_rate: float = 0.0,
) -> dict[str, Any]:
    """Aggregate independent OOS windows without bridging the gaps between them.

    Only within-window bar returns are pooled; no return is computed across a
    window boundary. Window returns are compounded in time order.
    """
    nonempty = [(equity, fills) for equity, fills in windows if equity]
    if not nonempty:
        return {"status": "insufficient_data", "reason": "empty_equity"}
    returns: list[float] = []
    for equity, _ in nonempty:
        returns.extend(_equity_returns(equity))
    return _summarise(
        returns,
        observations=sum(len(equity) for equity, _ in nonempty),
        trade_count=sum(len(fills) for _, fills in nonempty),
        total_cost=sum(float(f.fee) for _, fills in nonempty for f in fills),
        stale_bars=sum(_stale(equity) for equity, _ in nonempty),
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
    )
