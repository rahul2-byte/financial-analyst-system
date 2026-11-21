"""Summarize per-purpose model-call latency from persisted .finai records.

Usage: python backend/scripts/perf_report.py [DIR_OR_FILE ...]
Defaults to .finai/perf/model-calls.jsonl. Offline; reads local files only.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

FIELDS = (
    "ttft_ms",
    "total_ms",
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "cached_tokens",
    "retries",
)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    rank = max(0, math.ceil(q * len(ordered)) - 1)
    return ordered[rank]


def load_records(paths: list[Path]) -> list[dict[str, Any]]:
    files: list[Path] = []
    for path in paths:
        files.extend(sorted(path.glob("*.jsonl")) if path.is_dir() else [path])
    records: list[dict[str, Any]] = []
    for file in files:
        if not file.is_file():
            continue
        for line in file.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "purpose" in value:
                records.append(value)
    return records


def summarize(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("status", "completed") == "completed":
            groups[str(record["purpose"])].append(record)
    summary: dict[str, dict[str, Any]] = {}
    for purpose, items in sorted(groups.items()):
        stats: dict[str, Any] = {
            "n": len(items),
            "repair_calls": sum(1 for item in items if item.get("repair")),
        }
        for name in FIELDS:
            values = [
                float(item[name])
                for item in items
                if isinstance(item.get(name), (int, float))
            ]
            if values:
                stats[name] = {
                    "median": percentile(values, 0.5),
                    "p90": percentile(values, 0.9),
                }
        summary[purpose] = stats
    return summary


def render(summary: dict[str, dict[str, Any]]) -> str:
    lines: list[str] = []
    for purpose, stats in summary.items():
        lines.append(f"{purpose}  n={stats['n']}  repair_calls={stats['repair_calls']}")
        for name in FIELDS:
            if name in stats:
                cell = stats[name]
                lines.append(
                    f"  {name:<18} median={cell['median']:>10.1f}  p90={cell['p90']:>10.1f}"
                )
    return "\n".join(lines) if lines else "no completed model-call records found"


def main(argv: list[str]) -> int:
    paths = [Path(arg) for arg in argv] or [Path(".finai/perf/model-calls.jsonl")]
    print(render(summarize(load_records(paths))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
