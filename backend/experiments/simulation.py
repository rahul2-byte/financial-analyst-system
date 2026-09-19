from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from experiments.schemas import CostSpec, PortfolioLimits


@dataclass(frozen=True)
class Fill:
    timestamp: str
    ticker: str
    quantity: float
    price: float
    fee: float
    total_cost: float
    side: str
    reason: str


@dataclass(frozen=True)
class SimulationResult:
    fills: tuple[Fill, ...]
    equity: tuple[dict[str, Any], ...]
    ending_cash: float


def constrain_weights(
    requested: dict[str, float],
    *,
    limits: PortfolioLimits,
    sectors: dict[str, str] | None = None,
    previous: dict[str, float] | None = None,
) -> tuple[dict[str, float], dict[str, str]]:
    sectors = sectors or {}
    previous = previous or {}
    accepted: dict[str, float] = {}
    reasons: dict[str, str] = {}
    for ticker in sorted(requested):
        weight = max(0.0, min(float(requested[ticker]), limits.max_asset_weight))
        if weight != requested[ticker]:
            reasons[ticker] = "max_asset_weight"
        accepted[ticker] = weight
    ranked = sorted(accepted, key=lambda ticker: (-accepted[ticker], ticker))
    for ticker in ranked[limits.max_holdings :]:
        if accepted[ticker] > 0:
            accepted[ticker] = 0.0
            reasons[ticker] = "max_holdings"
    gross = sum(accepted.values())
    gross_cap = min(limits.max_gross_exposure, 1.0 - limits.min_cash_weight)
    if gross > gross_cap:
        scale = gross_cap / gross
        accepted = {ticker: weight * scale for ticker, weight in accepted.items()}
        reasons.update({ticker: "max_gross_exposure" for ticker in accepted})
    if limits.max_sector_weight is not None:
        for sector in sorted(set(sectors.values())):
            members = [ticker for ticker in accepted if sectors.get(ticker) == sector]
            total = sum(accepted[ticker] for ticker in members)
            if total > limits.max_sector_weight:
                scale = limits.max_sector_weight / total
                for ticker in members:
                    accepted[ticker] *= scale
                    reasons[ticker] = "max_sector_weight"
    turnover = sum(
        abs(accepted.get(ticker, 0.0) - previous.get(ticker, 0.0))
        for ticker in set(accepted) | set(previous)
    )
    if turnover > limits.max_turnover and turnover > 0:
        scale = limits.max_turnover / turnover
        accepted = {
            ticker: previous.get(ticker, 0.0)
            + (weight - previous.get(ticker, 0.0)) * scale
            for ticker, weight in accepted.items()
        }
        reasons.update({ticker: "max_turnover" for ticker in accepted})
    return accepted, reasons


def simulate(
    bars: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    initial_cash: float,
    costs: CostSpec,
    limits: PortfolioLimits,
) -> SimulationResult:
    bars = bars.sort_values(["ticker", "timestamp"]).copy()
    targets = targets.sort_values(["ticker", "timestamp"]).copy()
    cash = float(initial_cash)
    holdings: dict[str, float] = {}
    fills: list[Fill] = []
    equity: list[dict[str, Any]] = []
    previous_weights: dict[str, float] = {}
    for timestamp in sorted(set(bars["timestamp"])):
        current = bars[bars["timestamp"] == timestamp]
        pending = targets[targets["timestamp"] == timestamp]
        if not pending.empty:
            prices = {str(row.ticker): float(row.open) for row in current.itertuples()}
            total_equity = cash + sum(
                holdings.get(ticker, 0.0) * prices.get(ticker, 0.0)
                for ticker in holdings
            )
            requested = {
                str(row.ticker): float(row.desired_weight)
                for row in pending.itertuples()
            }
            weights, reasons = constrain_weights(
                requested, limits=limits, previous=previous_weights
            )
            previous_weights = weights
            for ticker, weight in weights.items():
                if ticker not in prices or total_equity <= 0:
                    continue
                desired_qty = weight * total_equity / prices[ticker]
                quantity = desired_qty - holdings.get(ticker, 0.0)
                if not limits.allow_fractional:
                    quantity = float(int(quantity))
                if quantity == 0:
                    continue
                price = prices[ticker] * (
                    1
                    + (costs.spread_bps + costs.slippage_bps)
                    / 10000
                    * (1 if quantity > 0 else -1)
                )
                fee = abs(quantity * price) * costs.commission_bps / 10000
                total = quantity * price + fee
                if quantity > 0 and total > cash:
                    continue
                cash -= total
                holdings[ticker] = holdings.get(ticker, 0.0) + quantity
                fills.append(
                    Fill(
                        str(timestamp),
                        ticker,
                        quantity,
                        price,
                        fee,
                        abs(total),
                        "buy" if quantity > 0 else "sell",
                        reasons.get(ticker, "target"),
                    )
                )
        mark = {str(row.ticker): float(row.close) for row in current.itertuples()}
        equity.append(
            {
                "timestamp": str(timestamp),
                "cash": cash,
                "equity": cash
                + sum(
                    holdings.get(ticker, 0.0) * mark.get(ticker, 0.0)
                    for ticker in holdings
                ),
            }
        )
    return SimulationResult(tuple(fills), tuple(equity), cash)
