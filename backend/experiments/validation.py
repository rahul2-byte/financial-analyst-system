from __future__ import annotations

from dataclasses import dataclass

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
    if min(minimum_train_bars, test_bars, step_bars) <= 0:
        raise ValueError("split sizes must be positive")
    if mode not in {"expanding", "rolling"}:
        raise ValueError("mode must be expanding or rolling")
    values = list(timestamps)
    splits: list[TimeSplit] = []
    start = minimum_train_bars
    counter = 0
    while start + test_bars <= len(values):
        train_start = 0 if mode == "expanding" else max(0, start - minimum_train_bars)
        train = tuple(range(train_start, start))
        test = tuple(range(start, start + test_bars))
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
    if embargo_bars < 0:
        raise ValueError("embargo_bars must be non-negative")
    result: list[TimeSplit] = []
    for split in splits:
        held_start = event_start.iloc[split.test[0]]
        held_end = event_end.iloc[split.test[-1]]
        train = tuple(
            index
            for index in split.train
            if event_end.iloc[index] <= held_start
            or event_start.iloc[index] >= held_end
        )
        embargo = tuple(range(split.test[-1] + 1, split.test[-1] + 1 + embargo_bars))
        result.append(TimeSplit(split.split_id, train, split.test, embargo))
    return tuple(result)
