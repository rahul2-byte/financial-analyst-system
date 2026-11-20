from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TimeSplit:
    split_id: str
    train: tuple[int, ...]
    test: tuple[int, ...]
    embargo: tuple[int, ...]


def make_splits(
    timestamps: pd.Series,
    *,
    minimum_train_bars: int,
    test_bars: int,
    step_bars: int,
    mode: str = "expanding",
) -> tuple[TimeSplit, ...]:
    """Walk-forward splits over unique sorted timestamps.

    Windows are defined in time, not row position, so in a ticker-major frame
    every ticker shares the same train and test windows. Split members are
    row positions of ``timestamps``.
    """
    if min(minimum_train_bars, test_bars, step_bars) <= 0:
        raise ValueError("split sizes must be positive")
    if mode not in {"expanding", "rolling"}:
        raise ValueError("mode must be expanding or rolling")
    values = pd.Series(list(timestamps))
    unique = pd.Index(sorted(values.unique()))
    if not unique.is_monotonic_increasing:  # pragma: no cover - sorted above
        raise ValueError("timestamps must be time-ordered")
    positions = values.map({stamp: i for i, stamp in enumerate(unique)}).to_numpy()
    splits: list[TimeSplit] = []
    start = minimum_train_bars
    counter = 0
    while start + test_bars <= len(unique):
        train_start = 0 if mode == "expanding" else max(0, start - minimum_train_bars)
        train = tuple(
            int(i)
            for i in np.flatnonzero((positions >= train_start) & (positions < start))
        )
        test = tuple(
            int(i)
            for i in np.flatnonzero(
                (positions >= start) & (positions < start + test_bars)
            )
        )
        splits.append(TimeSplit(f"split-{counter}", train, test, ()))
        counter += 1
        start += step_bars
    return tuple(splits)


def purge_splits(
    splits: tuple[TimeSplit, ...],
    event_start: pd.Series,
    event_end: pd.Series,
    *,
    embargo_bars: int,
) -> tuple[TimeSplit, ...]:
    """Purge train rows whose label window overlaps the test window.

    The embargo is the next ``embargo_bars`` unique timestamps after the test
    window, expressed as row positions across all tickers.
    """
    if embargo_bars < 0:
        raise ValueError("embargo_bars must be non-negative")
    unique = pd.Index(sorted(event_start.unique()))
    result: list[TimeSplit] = []
    for split in splits:
        held_start = event_start.iloc[list(split.test)].min()
        held_end = event_end.iloc[list(split.test)].max()
        train = tuple(
            index
            for index in split.train
            if event_end.iloc[index] <= held_start
            or event_start.iloc[index] >= held_end
        )
        last_test = event_start.iloc[list(split.test)].max()
        after = unique[unique > last_test][:embargo_bars]
        embargo = tuple(
            int(i) for i in np.flatnonzero(event_start.isin(after).to_numpy())
        )
        result.append(TimeSplit(split.split_id, train, split.test, embargo))
    return tuple(result)
