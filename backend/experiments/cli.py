from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.datasets import load_dataset
from experiments.features import feature_fingerprint, generate_features
from experiments.metrics import calculate_metrics
from experiments.registry import ExperimentRegistry
from experiments.schemas import ExperimentSpec
from experiments.signals import generate_signals
from experiments.simulation import simulate
from experiments.validation import make_splits, purge_splits


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
        if spec.validation.label_horizon_bars:
            event_start = features["timestamp"]
            event_end = event_start + (
                features["timestamp"].diff().median()
                * spec.validation.label_horizon_bars
            )
            splits = purge_splits(
                splits,
                event_start,
                event_end,
                embargo_bars=spec.validation.embargo_bars,
            )
        oos_indices = sorted({index for split in splits for index in split.test})
        oos = signals.iloc[oos_indices]
        # A signal observed at bar t can execute only at the next bar's open.
        oos = oos.copy()
        oos["timestamp"] = oos.groupby("ticker")["timestamp"].shift(-1)
        oos = oos.dropna(subset=["timestamp"])
        result = simulate(
            features.iloc[oos_indices],
            oos,
            initial_cash=spec.initial_cash,
            costs=spec.costs,
            limits=spec.limits,
        )
        metrics = calculate_metrics(result.equity, result.fills)
        registry.complete(
            run_id,
            {
                "feature_fingerprint": feature_fingerprint(features),
                "split_count": len(splits),
                "metrics": metrics,
                "validation": "oos" if oos_indices else "insufficient_data",
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
