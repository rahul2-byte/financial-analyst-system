from datetime import UTC, datetime

import pytest
from experiments.datasets import DatasetError, create_dataset, load_dataset
from experiments.schemas import (
    CostSpec,
    DatasetRef,
    ExperimentSpec,
    PortfolioLimits,
    ValidationSpec,
)


def _rows() -> list[dict[str, object]]:
    return [
        {
            "ticker": "AAA",
            "timestamp": "2026-01-02T00:00:00+00:00",
            "open": 101,
            "high": 102,
            "low": 100,
            "close": 101,
            "volume": 10,
        },
        {
            "ticker": "AAA",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "volume": 10,
        },
    ]


def test_dataset_hashes_and_reloads(tmp_path):
    created = create_dataset(
        tmp_path,
        dataset_id="fixture",
        source="fixture",
        source_bytes=b"raw",
        rows=_rows(),
        currency="USD",
        timezone="UTC",
        adjustment="unadjusted",
        as_of=datetime(2026, 1, 3, tzinfo=UTC),
    )
    loaded = load_dataset(tmp_path, "fixture")
    assert loaded == created
    assert len(created.normalized_hash) == 64


def test_dataset_rejects_duplicate_rows(tmp_path):
    with pytest.raises(DatasetError, match="duplicate"):
        create_dataset(
            tmp_path,
            dataset_id="fixture",
            source="fixture",
            source_bytes=b"raw",
            rows=_rows() + [_rows()[0]],
            currency="USD",
            timezone="UTC",
            adjustment="unadjusted",
            as_of=datetime(2026, 1, 3, tzinfo=UTC),
        )


def test_experiment_spec_rejects_currency_mismatch():
    with pytest.raises(ValueError, match="currency"):
        ExperimentSpec(
            strategy_id="x",
            strategy_version="1",
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 2, tzinfo=UTC),
            initial_cash=1000,
            base_currency="EUR",
            dataset=DatasetRef(
                dataset_id="d",
                source="s",
                source_hash="a" * 64,
                normalized_hash="b" * 64,
                currency="USD",
                timezone="UTC",
                adjustment="unadjusted",
                as_of=datetime(2026, 1, 1, tzinfo=UTC),
                tickers=("AAA",),
            ),
            costs=CostSpec(commission_bps=1, spread_bps=1, slippage_bps=1),
            limits=PortfolioLimits(
                max_asset_weight=1,
                max_gross_exposure=1,
                min_cash_weight=0,
                max_holdings=1,
                max_turnover=2,
            ),
            validation=ValidationSpec(
                minimum_train_bars=1, test_bars=1, step_bars=1, embargo_bars=0
            ),
        )
