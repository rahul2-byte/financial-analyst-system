from datetime import UTC, datetime

from experiments.cli import run
from experiments.datasets import create_dataset
from experiments.registry import ExperimentRegistry
from experiments.schemas import (
    CostSpec,
    DatasetRef,
    ExperimentSpec,
    PortfolioLimits,
    ValidationSpec,
)


def test_offline_experiment_runs_and_registers_oos_result(tmp_path):
    rows = [
        {
            "ticker": "AAA",
            "timestamp": f"2026-01-{day:02d}T00:00:00+00:00",
            "open": day + 10,
            "high": day + 11,
            "low": day + 9,
            "close": day + 10,
            "volume": 100,
        }
        for day in range(1, 11)
    ]
    dataset = create_dataset(
        tmp_path,
        dataset_id="d",
        source="fixture",
        source_bytes=b"fixture",
        rows=rows,
        currency="USD",
        timezone="UTC",
        adjustment="unadjusted",
        as_of=datetime(2026, 1, 11, tzinfo=UTC),
    )
    spec = ExperimentSpec(
        strategy_id="fixture",
        strategy_version="1",
        dataset=DatasetRef(
            dataset_id=dataset.dataset_id,
            source=dataset.source,
            source_hash=dataset.source_hash,
            normalized_hash=dataset.normalized_hash,
            currency=dataset.currency,
            timezone=dataset.timezone,
            adjustment="unadjusted",
            as_of=dataset.as_of,
            tickers=("AAA",),
        ),
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 11, tzinfo=UTC),
        initial_cash=1000,
        base_currency="USD",
        costs=CostSpec(commission_bps=1, spread_bps=1, slippage_bps=1),
        limits=PortfolioLimits(
            max_asset_weight=1,
            max_gross_exposure=1,
            min_cash_weight=0,
            max_holdings=1,
            max_turnover=2,
        ),
        validation=ValidationSpec(
            minimum_train_bars=3, test_bars=2, step_bars=2, embargo_bars=0
        ),
    )
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(spec.model_dump_json(), encoding="utf-8")
    result = run(tmp_path, tmp_path, spec_path)
    record = ExperimentRegistry(tmp_path).load(result["run_id"])
    assert record["status"] == "completed"
    assert record["artifacts"]["validation"] == "oos"
