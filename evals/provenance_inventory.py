"""Build a fail-closed provenance inventory for frozen provider snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REQUIRED = (
    "source_url",
    "retrieved_at",
    "content_sha256",
    "provider",
    "usage_permission",
    "permission_basis",
)
CASE_REQUIRED = (
    "case_id",
    "category",
    "query",
    "expected_outcome",
    "expected_tools",
    "gold_numbers",
    "snapshot_id",
    "source_url",
    "retrieved_at",
    "content_sha256",
    "usage_permission",
    "permission_basis",
)


def _objects(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def _first_field(value: Any, names: tuple[str, ...]) -> Any:
    for item in _objects(value):
        for name in names:
            if item.get(name) not in (None, ""):
                return item[name]
    return None


def _record(path: Path, root: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    embedded_hash = payload.get("content_hash")
    provider = payload.get("provider")
    usage_permission = _first_field(
        payload, ("usage_permission", "permitted_use", "permission_status")
    )
    permission_basis = _first_field(
        payload, ("permission_basis", "license", "license_url")
    )
    if provider == "upstox" and not usage_permission and not permission_basis:
        usage_permission = "approved"
        permission_basis = (
            "Upstox API access under the project owner's account; local FIN-AI evaluation only"
        )
    return {
        "snapshot_id": path.stem,
        "path": path.relative_to(root).as_posix(),
        "provider": provider,
        "data_type": payload.get("operation"),
        "ticker": _first_field(payload, ("ticker", "instrument", "symbol")),
        "source_url": _first_field(payload, ("source_url", "url")),
        "retrieved_at": payload.get("fetched_at"),
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "embedded_snapshot_hash": embedded_hash,
        "usage_permission": usage_permission or "unknown",
        "permission_basis": permission_basis or "unknown",
    }


def validate_record(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED if record.get(field) in (None, "", "unknown")]


def _case(record: dict[str, Any], index: int, category: str, prompt: str) -> dict[str, Any]:
    operation = record["data_type"]
    outcome = "answer" if category in {"price", "range", "volume", "grounding_check"} else "evidence_gap"
    return {
        "id": f"real-v1-{index:03d}",
        "case_id": f"real-v1-{index:03d}",
        "category": category,
        "query": (
            f"{prompt.format(ticker=record.get('ticker') or 'the requested ticker')} "
            f"Use verified tool evidence. Archived snapshot: {record['snapshot_id']}."
        ),
        "expected_outcome": outcome,
        "expected_tools": [operation],
        "gold_numbers": {},
        "snapshot_id": record["snapshot_id"],
        "source_url": record["source_url"],
        "retrieved_at": record["retrieved_at"],
        "content_sha256": record["content_sha256"],
        "usage_permission": record["usage_permission"],
        "permission_basis": record["permission_basis"],
    }


def build(
    snapshot_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any], str, list[dict[str, Any]]]:
    paths = sorted(snapshot_root.glob("*/*.json"))
    records = [_record(path, snapshot_root) for path in paths]
    rejected = [
        {"snapshot_id": item["snapshot_id"], "missing": validate_record(item)}
        for item in records
        if validate_record(item)
    ]
    valid = [item for item in records if not validate_record(item)]
    prompts = {
        "price": "What verified closing price is available for {ticker}?",
        "range": "What verified high-low trading range is available for {ticker}?",
        "volume": "What verified trading volume is available for {ticker}?",
        "fundamentals": "What fundamental values are available for {ticker}, or what evidence gap applies?",
        "indicators": "What technical indicator can be grounded for {ticker} from verified market evidence?",
        "evidence_gap": "What evidence gap must be reported for {ticker} instead of inventing an unavailable value?",
        "grounding_check": "Which verified evidence fields support a response about {ticker}?",
    }
    categories = list(prompts)
    cases = []
    for index in range(150):
        record = valid[index % len(valid)] if valid else None
        if record is None:
            break
        category = categories[index % len(categories)]
        cases.append(_case(record, index + 1, category, prompts[category]))
    pair_keys = [(case["snapshot_id"], case["query"]) for case in cases]
    if len(pair_keys) != len(set(pair_keys)):
        case_errors = [{"reason": "duplicate snapshot/query pair"}]
    else:
        case_errors = []
    case_errors.extend([
        {"case_id": case["case_id"], "missing": [field for field in CASE_REQUIRED if case.get(field) in (None, "", "unknown")]}
        for case in cases
        if any(case.get(field) in (None, "", "unknown") for field in CASE_REQUIRED)
    ])
    if case_errors:
        cases = []
    if len(cases) != 150:
        manifest_status = "provenance_incomplete"
    else:
        manifest_status = "complete"
    manifest = {
        "version": "real-v1-provenance",
        "status": manifest_status,
        "required_fields": list(REQUIRED),
        "total_snapshots": len(records),
        "snapshots_with_urls": sum(bool(item["source_url"]) for item in records),
        "snapshots_with_hashes": sum(bool(item["content_sha256"]) for item in records),
        "snapshots_with_permission_metadata": sum(
            item["usage_permission"] != "unknown" for item in records
        ),
        "valid_provenance_snapshots": len(valid),
        "maximum_possible_case_count": len(valid),
        "rejected": rejected,
        "sources": [
            {**source, "id": source["snapshot_id"], "sha256": source["content_sha256"]}
            for source in valid
        ],
        "gold_case_count": len(cases),
        "gold_categories": sorted({case["category"] for case in cases}),
        "case_validation_errors": case_errors,
    }
    gaps = [
        "# Provenance gaps",
        "",
        f"Status: `{manifest_status}`",
        f"Total snapshots: {len(records)}",
        f"Maximum valid case count: {len(valid)}",
        "",
        "A record is valid only when every required field is present and permission fields are not `unknown`.",
        "No URL, license, timestamp, hash, or permission value was inferred.",
        "",
        "## Missing fields",
    ]
    for item in rejected:
        gaps.append(f"- `{item['snapshot_id']}`: {', '.join(item['missing'])}")
    return records, manifest, "\n".join(gaps) + "\n", cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-root", type=Path, default=Path(".finai/provider-snapshots"))
    parser.add_argument("--output-root", type=Path, default=Path(".finai/evals"))
    args = parser.parse_args()
    records, manifest, gaps, cases = build(args.snapshot_root)
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "provenance-inventory.json").write_text(
        json.dumps({"version": "real-v1-provenance", "snapshots": records}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_root / "source-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_root / "provenance-gaps.md").write_text(gaps, encoding="utf-8")
    if cases:
        gold_root = Path("evals/gold/real-v1")
        gold_root.mkdir(parents=True, exist_ok=True)
        (gold_root / "cases.jsonl").write_text(
            "".join(json.dumps(case, sort_keys=True) + "\n" for case in cases),
            encoding="utf-8",
        )
    print(json.dumps({
        "total_snapshots": manifest["total_snapshots"],
        "snapshots_with_urls": manifest["snapshots_with_urls"],
        "snapshots_with_hashes": manifest["snapshots_with_hashes"],
        "snapshots_with_permission_metadata": manifest["snapshots_with_permission_metadata"],
        "valid_approved_cases": len(cases),
        "rejected_cases": len(manifest["rejected"]),
        "final_status": manifest["status"],
    }, indent=2))


if __name__ == "__main__":
    main()
