"""Aggregate recorded typed run events; never contacts a provider."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evals.live_metrics import aggregate_run_events


def _read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid event JSON on line {line_number}") from exc
        if not isinstance(value, dict):
            raise TypeError(f"event on line {line_number} is not an object")
        events.append(value)
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pricing", type=Path)
    args = parser.parse_args()
    try:
        events = _read_events(args.events)
        pricing = json.loads(args.pricing.read_text()) if args.pricing else None
        if pricing is not None and not isinstance(pricing, dict):
            raise ValueError("pricing manifest must be an object")
        result = aggregate_run_events(events, pricing)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
