from __future__ import annotations

from math import sqrt
from typing import Any


def calculate_metrics(
    equity: tuple[dict[str, Any], ...], fills: tuple[Any, ...]
) -> dict[str, Any]:
    values = [float(item["equity"]) for item in equity]
    if not values:
        return {"status": "insufficient_data", "reason": "empty_equity"}
    returns = [
        (values[index] / values[index - 1]) - 1
        for index in range(1, len(values))
        if values[index - 1] != 0
    ]
    peak = values[0]
    drawdowns: list[float] = []
    for value in values:
        peak = max(peak, value)
        drawdowns.append((value - peak) / peak if peak else 0.0)
    result: dict[str, Any] = {
        "status": "measured",
        "trade_count": len(fills),
        "cumulative_return": values[-1] / values[0] - 1 if values[0] else None,
        "max_drawdown": min(drawdowns),
        "observations": len(values),
        "total_cost": sum(float(fill.fee) for fill in fills),
    }
    if len(returns) >= 2:
        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
        result["volatility"] = sqrt(variance)
        result["sharpe_like"] = mean / sqrt(variance) if variance > 0 else None
    else:
        result["volatility"] = None
        result["sharpe_like"] = None
    return result
