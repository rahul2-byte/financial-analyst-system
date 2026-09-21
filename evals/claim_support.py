"""Score repository JSONL claim labels and agreement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evals.agreement import agreement_summary
from evals.labels import validate_claim_support_labels


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    labels = [json.loads(line) for line in args.labels.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload: dict[str, Any] = {
        "validation_errors": validate_claim_support_labels(labels),
        "agreement": agreement_summary(labels),
        "label_count": len(labels),
        "status": "measured" if labels and not validate_claim_support_labels(labels) else "insufficient_evidence",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0 if not payload["validation_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
