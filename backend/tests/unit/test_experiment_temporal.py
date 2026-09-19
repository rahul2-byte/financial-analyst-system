from datetime import UTC

import pandas as pd
from experiments.datasets import create_dataset
from experiments.features import generate_features
from experiments.signals import generate_signals
from experiments.validation import make_splits, purge_splits
from pandas.testing import assert_series_equal


def _dataset(tmp_path):
    rows = [
        {
            "ticker": "AAA",
            "timestamp": f"2026-01-{day:02d}T00:00:00+00:00",
            "open": day,
            "high": day + 1,
            "low": max(1, day - 1),
            "close": day,
            "volume": 10,
        }
        for day in range(1, 9)
    ]
    return create_dataset(
        tmp_path,
        dataset_id="d",
        source="fixture",
        source_bytes=b"x",
        rows=rows,
        currency="USD",
        timezone="UTC",
        adjustment="unadjusted",
        as_of=pd.Timestamp("2026-01-09", tz="UTC").to_pydatetime(),
    )


def test_features_are_prefix_invariant(tmp_path):
    dataset = _dataset(tmp_path)
    all_features = generate_features(dataset, ema_window=3)
    prefix = generate_features(
        dataset.model_copy(update={"rows": dataset.rows[:5]}), ema_window=3
    )
    assert_series_equal(
        all_features.loc[:4, "ema"].reset_index(drop=True),
        prefix["ema"].reset_index(drop=True),
        check_names=False,
    )
    assert generate_signals(all_features).loc[3, "desired_weight"] == 1.0


def test_splits_are_chronological_and_purge_overlap():
    timestamps = pd.Series(pd.date_range("2026-01-01", periods=8, tz=UTC))
    splits = make_splits(timestamps, minimum_train_bars=3, test_bars=2, step_bars=2)
    assert splits[0].train == (0, 1, 2)
    starts = timestamps
    ends = timestamps + pd.to_timedelta(1, unit="D")
    purged = purge_splits(splits, starts, ends, embargo_bars=1)
    assert purged[0].embargo == (5,)
