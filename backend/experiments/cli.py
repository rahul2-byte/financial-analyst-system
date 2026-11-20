from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from experiments.datasets import load_dataset
from experiments.features import (
    feature_fingerprint,
    generate_features,
    infer_bar_interval,
)
from experiments.metrics import aggregate_window_metrics, calculate_metrics
from experiments.registry import ExperimentRegistry
from experiments.schemas import ExperimentSpec
from experiments.signals import generate_signals
from experiments.simulation import simulate
from experiments.validation import make_splits, purge_splits

PERIODS_PER_YEAR = {"1d": 252}


def run(dataset_root: Path, artifact_root: Path, spec_path: Path) -> dict[str, str]:
    spec = ExperimentSpec.model_validate_json(spec_path.read_text(encoding="utf-8"))
    dataset = load_dataset(dataset_root, spec.dataset.dataset_id)
    registry = ExperimentRegistry(artifact_root)
    run_id = registry.create(spec.model_dump(mode="json"))
    try:
        features = generate_features(dataset)
        signals = generate_signals(features)
        splits = make_splits(
            features["timestamp"],
            minimum_train_bars=spec.validation.minimum_train_bars,
            test_bars=spec.validation.test_bars,
            step_bars=spec.validation.step_bars,
            mode=spec.validation.mode,
        )
        # Purge and embargo are always applied. Signals execute at the next bar's
        # open, so a decision label spans at least 1 bar, and a minimum embargo
        # of 1 bar is kept even when the spec says 0. Silently skipping them (as
        # label_horizon_bars=0 used to) lets train rows touch the test window.
        horizon = max(spec.validation.label_horizon_bars, 1)
        embargo_bars = max(spec.validation.embargo_bars, 1)
        bar_interval = infer_bar_interval(features["timestamp"])
        event_start = features["timestamp"]
        splits = purge_splits(
            splits,
            event_start,
            event_start + bar_interval * horizon,
            embargo_bars=embargo_bars,
        )
        periods_per_year = PERIODS_PER_YEAR[spec.bar_frequency]
        window_results = []
        window_metrics: list[dict[str, Any]] = []
        last_end = None
        for split in splits:
            if not split.test:
                continue
            idx = list(split.test)
            window_ts = features["timestamp"].iloc[idx]
            if last_end is not None and window_ts.min() <= last_end:
                # Overlapping windows would double-count bars in the aggregate.
                continue
            last_end = window_ts.max()
            bars = features.iloc[idx]
            oos = signals.iloc[idx].copy()
            # A signal observed at bar t executes at the next bar's open, within
            # this window only; the last bar's signal is dropped, never bridged.
            oos["timestamp"] = oos.groupby("ticker")["timestamp"].shift(-1)
            oos = oos.dropna(subset=["timestamp"])
            if not (oos["timestamp"] >= oos["available_at"]).all():
                raise ValueError("execution scheduled before feature availability")
            result = simulate(
                bars,
                oos,
                initial_cash=spec.initial_cash,
                costs=spec.costs,
                limits=spec.limits,
            )
            window_results.append((result.equity, result.fills))
            window_metrics.append(
                {
                    "split_id": split.split_id,
                    "start": str(window_ts.min()),
                    "end": str(last_end),
                    **calculate_metrics(
                        result.equity,
                        result.fills,
                        periods_per_year=periods_per_year,
                        risk_free_rate=spec.risk_free_rate,
                    ),
                }
            )
        metrics = aggregate_window_metrics(
            window_results,
            periods_per_year=periods_per_year,
            risk_free_rate=spec.risk_free_rate,
        )
        registry.complete(
            run_id,
            {
                "feature_fingerprint": feature_fingerprint(features),
                "split_count": len(splits),
                "effective_label_horizon_bars": horizon,
                "effective_embargo_bars": embargo_bars,
                "metrics": metrics,
                "window_metrics": window_metrics,
                "validation": "oos" if window_results else "insufficient_data",
            },
        )
    except Exception as exc:
        registry.fail(run_id, str(exc))
        raise
    return {"run_id": run_id, "status": "completed"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a deterministic offline experiment"
    )
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.dataset_root, args.artifact_root, args.spec), sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
