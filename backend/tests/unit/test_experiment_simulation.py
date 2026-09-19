import pandas as pd
from experiments.metrics import calculate_metrics
from experiments.schemas import CostSpec, PortfolioLimits
from experiments.simulation import simulate


def test_simulation_uses_costs_and_reports_equity():
    bars = pd.DataFrame(
        [
            {"ticker": "AAA", "timestamp": "2026-01-01", "open": 100, "close": 100},
            {"ticker": "AAA", "timestamp": "2026-01-02", "open": 110, "close": 110},
        ]
    )
    targets = pd.DataFrame(
        [{"ticker": "AAA", "timestamp": "2026-01-02", "desired_weight": 1.0}]
    )
    result = simulate(
        bars,
        targets,
        initial_cash=1000,
        costs=CostSpec(commission_bps=10, spread_bps=10, slippage_bps=0),
        limits=PortfolioLimits(
            max_asset_weight=1,
            max_gross_exposure=1,
            min_cash_weight=0,
            max_holdings=1,
            max_turnover=2,
        ),
    )
    assert result.fills[0].price > 110
    assert calculate_metrics(result.equity, result.fills)["trade_count"] == 1


def test_constraints_limit_holdings_and_gross_exposure():
    from experiments.simulation import constrain_weights

    weights, reasons = constrain_weights(
        {"B": 0.8, "A": 0.8},
        limits=PortfolioLimits(
            max_asset_weight=1,
            max_gross_exposure=0.5,
            min_cash_weight=0,
            max_holdings=1,
            max_turnover=2,
        ),
    )
    assert sum(weights.values()) <= 0.5
    assert reasons
