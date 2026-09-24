"""Build and validate a frozen one-case-per-instrument Upstox benchmark."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import random
import re
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

_HASH = re.compile(r"^[0-9a-f]{64}$")


def parse_nse_equities(content: bytes) -> list[dict[str, Any]]:
    """Read the Upstox NSE BOD instrument file and retain cash equities."""
    try:
        value = json.loads(gzip.decompress(content))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid compressed Upstox instrument master") from exc
    if not isinstance(value, list):
        raise TypeError("Upstox instrument master must be a JSON array")
    unique: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        key = item.get("instrument_key")
        symbol = item.get("trading_symbol")
        if (
            item.get("segment") == "NSE_EQ"
            and item.get("instrument_type") == "EQ"
            and isinstance(key, str)
            and key.startswith("NSE_EQ|")
            and isinstance(symbol, str)
            and symbol
        ):
            unique.setdefault(key, item)
    return [unique[key] for key in sorted(unique)]


def select_instruments(
    instruments: list[dict[str, Any]], *, count: int = 150, seed: int = 20260923
) -> list[dict[str, Any]]:
    """Select a reproducible sample from a frozen, sorted instrument universe."""
    if count < 1:
        raise ValueError("count must be positive")
    unique = {
        item["instrument_key"]: item
        for item in instruments
        if isinstance(item.get("instrument_key"), str)
        and item["instrument_key"].startswith("NSE_EQ|")
    }
    keys = sorted(unique)
    if len(keys) < count:
        raise ValueError(f"only {len(keys)} unique instruments available; need {count}")
    selected = random.Random(seed).sample(keys, count)
    return [unique[key] for key in selected]


def build_cases(
    instruments: list[dict[str, Any]],
    candles_by_key: dict[str, list[dict[str, Any]]],
    *,
    trading_date: str,
    source_url: str,
    permission_basis: str,
    retrieved_at: datetime,
    source_payloads: dict[str, Any] | None = None,
    source_url_template: str | None = None,
) -> list[dict[str, Any]]:
    """Create one answer case per key from the requested daily candle."""
    target_date = date.fromisoformat(trading_date)
    cases = []
    for index, instrument in enumerate(instruments, 1):
        key = instrument["instrument_key"]
        candles = candles_by_key.get(key, [])
        match = next(
            (
                candle
                for candle in candles
                if date.fromisoformat(str(candle["timestamp"])[:10]) == target_date
            ),
            None,
        )
        close = match.get("close") if match else None
        if match is not None and (
            not isinstance(close, (int, float))
            or isinstance(close, bool)
            or not math.isfinite(close)
            or close <= 0
        ):
            raise ValueError(f"{key}: invalid close on {trading_date}")
        case_source_url = (
            source_url_template.format(instrument_key=key)
            if source_url_template
            else source_url
        )
        snapshot = {
            "provider": "upstox",
            "operation": "historical_candle",
            "source_url": case_source_url,
            "retrieved_at": retrieved_at.isoformat(),
            "usage_permission": "approved",
            "permission_basis": permission_basis,
            "instrument_key": key,
            "trading_date": trading_date,
            "instrument": instrument,
            "candle": match,
            "response_payload": (source_payloads or {}).get(key),
        }
        snapshot_id = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        symbol = str(instrument.get("trading_symbol") or key)
        cases.append(
            {
                "case_id": f"upstox-{index:03d}",
                "category": "price",
                "instrument_key": key,
                "trading_symbol": symbol,
                "trading_date": trading_date,
                "query": (
                    f"Report whether a verified closing price is available for {symbol} "
                    f"on {trading_date}. Use the data tool and cite its evidence."
                ),
                "expected_outcome": "answer" if match else "evidence_gap",
                "gold_numbers": {"close": close} if match else {},
                "snapshot_id": snapshot_id,
                "source_url": case_source_url,
                "retrieved_at": retrieved_at.isoformat(),
                "content_sha256": snapshot_id,
                "frozen_candle": match,
                "data_collection_duration_ms": (
                    (source_payloads or {}).get(key, {}).get("request_duration_ms")
                ),
                "usage_permission": "approved",
                "permission_basis": permission_basis,
                "configuration": {
                    "mode": "guided",
                    "publish_reports": True,
                    "allowed_tools": ["data:fetch_stock_data"],
                },
                "snapshot": snapshot,
            }
        )
    errors = validate_cases(cases, expected_count=len(instruments))
    if errors:
        raise ValueError("invalid generated cases: " + "; ".join(errors))
    return cases


def collect_live_cases(
    *,
    instrument_master: bytes,
    upstox_token: str,
    trading_date: str,
    permission_basis: str,
    count: int = 150,
    seed: int = 20260923,
) -> list[dict[str, Any]]:
    """Fetch and freeze a distinct-key sample from the authenticated Upstox API."""
    from datetime import timedelta

    from app.config import settings
    from app.observability.provider_archive import ProviderArchive, ProviderSnapshot
    from data.providers.upstox import UpstoxFetcher

    instruments = select_instruments(
        parse_nse_equities(instrument_master), count=count, seed=seed
    )
    fetcher = UpstoxFetcher(access_token=upstox_token)
    target = date.fromisoformat(trading_date)
    candles: dict[str, list[dict[str, Any]]] = {}
    payloads: dict[str, Any] = {}
    fetched_at = datetime.now().astimezone()
    start = datetime.combine(target, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(target + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    for instrument in instruments:
        key = instrument["instrument_key"]
        request_started = time.perf_counter()
        candles[key] = fetcher.fetch_candles(
            key,
            start=start,
            end=end,
        )
        payloads[key] = {
            "instrument_key": key,
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
            "candles": candles[key],
            "request_duration_ms": round(
                (time.perf_counter() - request_started) * 1000, 2
            ),
        }
    source_url = f"{settings.UPSTOX_BASE_URL.rstrip('/')}/v3/historical-candle/{{instrument_key}}/days/1"
    cases = build_cases(
        instruments,
        candles,
        trading_date=trading_date,
        source_url=source_url,
        permission_basis=permission_basis,
        retrieved_at=fetched_at,
        source_payloads=payloads,
        source_url_template=source_url,
    )
    archive = ProviderArchive(Path(".finai"))
    master_snapshot = archive.store(
        ProviderSnapshot(
            provider="upstox",
            operation="instrument_master",
            payload={
                "provider": "upstox",
                "operation": "instrument_master",
                "source_url": "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
                "sha256": hashlib.sha256(instrument_master).hexdigest(),
                "selected_instruments": instruments,
                "sample_count": count,
                "seed": seed,
            },
            fetched_at=fetched_at,
        )
    )
    for case in cases:
        archived = archive.store(
            ProviderSnapshot(
                provider="upstox",
                operation="historical_candle",
                payload=case["snapshot"],
                fetched_at=fetched_at,
            )
        )
        case["snapshot_id"] = archived.content_hash
        case["content_sha256"] = archived.content_hash
        case["instrument_master_snapshot_id"] = master_snapshot.content_hash
        case.pop("snapshot")
    return cases


def collect_instrument_master(url: str) -> bytes:
    """Fetch the official gzip-compressed NSE instrument master."""
    response = httpx.get(url, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    content = response.content
    gzip.decompress(content)
    return content


def validate_archive_cases(
    cases: list[dict[str, Any]], archive_root: Path
) -> list[str]:
    from app.observability.provider_archive import ProviderArchive

    archive = ProviderArchive(archive_root)
    errors = []
    for case in cases:
        try:
            snapshot = archive.load(str(case.get("snapshot_id", "")))
            master_snapshot = archive.load(
                str(case.get("instrument_master_snapshot_id", ""))
            )
        except (ValueError, RuntimeError) as exc:
            errors.append(f"{case.get('case_id')}: {exc}")
            continue
        payload = snapshot.payload
        master_payload = master_snapshot.payload
        if not isinstance(payload, dict):
            errors.append(f"{case.get('case_id')}: snapshot payload must be an object")
        else:
            candle = payload.get("candle")
            gold = case.get("gold_numbers", {})
            if (
                payload.get("instrument_key") != case.get("instrument_key")
                or payload.get("trading_date") != case.get("trading_date")
                or candle != case.get("frozen_candle")
                or (
                    case.get("expected_outcome") == "answer"
                    and (
                        not isinstance(candle, dict)
                        or candle.get("close") != gold.get("close")
                    )
                )
                or (
                    case.get("expected_outcome") == "evidence_gap"
                    and candle is not None
                )
            ):
                errors.append(
                    f"{case.get('case_id')}: case does not match archived snapshot"
                )
        if (
            not isinstance(master_payload, dict)
            or master_payload.get("provider") != "upstox"
            or master_payload.get("operation") != "instrument_master"
            or case.get("instrument_key")
            not in {
                item.get("instrument_key")
                for item in master_payload.get("selected_instruments", [])
                if isinstance(item, dict)
            }
        ):
            errors.append(
                f"{case.get('case_id')}: instrument absent from frozen master"
            )
    return errors


def score_artifacts(
    cases: list[dict[str, Any]], artifacts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Check benchmark outputs against frozen close/date facts, not prose quality."""
    by_id = {str(item.get("case_id")): item for item in artifacts}
    rows: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("case_id"))
        artifact = by_id.get(case_id)
        issues: list[str] = []
        if artifact is None:
            rows.append(
                {"case_id": case_id, "status": "missing_artifact", "issues": ["artifact_missing"]}
            )
            continue
        expected = case.get("expected_outcome")
        claims = artifact.get("claims")
        claims = claims if isinstance(claims, list) else []
        if expected == "evidence_gap":
            correct = (
                artifact.get("terminal_status") == "completed_with_limited_evidence"
                and not any(
                    isinstance(claim, dict) and claim.get("importance") == "major"
                    for claim in claims
                )
            )
            if not correct:
                issues.append("expected_evidence_gap_not_abstained")
            rows.append(
                {
                    "case_id": case_id,
                    "status": "expected_evidence_gap" if correct else "failed",
                    "issues": issues,
                }
            )
            continue

        if artifact.get("terminal_status") not in {"success", "completed"}:
            issues.append("answer_case_not_completed")
        if artifact.get("report_validation", {}).get("publication_status") != "passed":
            issues.append("publication_not_passed")
        candle = case.get("frozen_candle")
        gold_close = (case.get("gold_numbers") or {}).get("close")
        if (
            not isinstance(candle, dict)
            or candle.get("close") != gold_close
            or not isinstance(candle.get("timestamp"), str)
        ):
            issues.append("invalid_frozen_close_or_timestamp")
        else:
            try:
                observed_date = date.fromisoformat(str(candle["timestamp"])[:10])
                requested_date = date.fromisoformat(str(case["trading_date"]))
            except ValueError:
                issues.append("invalid_frozen_close_or_timestamp")
            else:
                if observed_date != requested_date:
                    issues.append("frozen_timestamp_does_not_match_requested_date")

        citations = {
            str(citation.get("citation_id")): citation
            for citation in artifact.get("citations", [])
            if isinstance(citation, dict) and citation.get("citation_id")
        }
        bound_rows = {"first": {"close": False, "timestamp": False}, "latest": {"close": False, "timestamp": False}}
        for claim in claims:
            if not isinstance(claim, dict) or claim.get("importance") != "major":
                continue
            text = str(claim.get("text") or "")
            refs = set(claim.get("numeric_refs") or [])
            evidence_refs = set(claim.get("evidence_refs") or [])
            source_is_cited = any(
                citation_id in citations
                and citations[citation_id].get("source_id") == "upstox_historical_candle"
                for citation_id in evidence_refs
            )
            if not source_is_cited:
                continue
            for row_name in ("first", "latest"):
                close_id = f"upstox_historical_candle:data.{row_name}.close"
                timestamp_id = f"upstox_historical_candle:data.{row_name}.timestamp"
                for fact_name, fact_id in (("close", close_id), ("timestamp", timestamp_id)):
                    if fact_id in refs and f"[[fact:{fact_id}]]" in text:
                        bound_rows[row_name][fact_name] = True
        bound = any(all(facts.values()) for facts in bound_rows.values())
        if not bound:
            issues.append("expected_close_and_timestamp_not_bound_in_major_claim")
        rows.append(
            {
                "case_id": case_id,
                "status": "fact_checks_passed" if not issues else "failed",
                "issues": issues,
            }
        )

    answer_rows = [row for row in rows if row["status"] != "expected_evidence_gap"]
    failed = sum(row["status"] != "fact_checks_passed" for row in answer_rows)
    deterministic_passed = not failed
    return {
        "status": (
            "pending_semantic_judge"
            if deterministic_passed
            else "deterministic_checks_failed"
        ),
        "deterministic_checks_passed": not failed,
        "semantic_judge_required": True,
        "case_count": len(rows),
        "answer_case_count": len(answer_rows),
        "fact_checks_passed": len(answer_rows) - failed,
        "expected_evidence_gaps": sum(
            row["status"] == "expected_evidence_gap" for row in rows
        ),
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=150)
    parser.add_argument("--seed", type=int, default=20260923)
    parser.add_argument(
        "--instrument-master-url",
        default="https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
    )
    parser.add_argument(
        "--permission-basis",
        default="Upstox API account; local FIN-AI evaluation only; no redistribution",
    )
    parser.add_argument("--confirm-local-evaluation-only", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    if args.validate_only:
        if not args.output.is_file():
            parser.error(f"manifest file does not exist: {args.output}")
        errors = validate_manifest_file(args.output, Path(".finai"))
        if errors:
            parser.error("manifest validation failed: " + "; ".join(errors))
        print(json.dumps({"status": "valid", "manifest": str(args.output)}, indent=2))
        return 0
    from app.config import settings

    if not args.confirm_local_evaluation_only:
        parser.error("requires --confirm-local-evaluation-only")
    if not settings.UPSTOX_ACCESS_TOKEN:
        parser.error("UPSTOX_ACCESS_TOKEN is not configured")
    if args.count < 1:
        parser.error("--count must be positive")
    try:
        master = collect_instrument_master(args.instrument_master_url)
        cases = collect_live_cases(
            instrument_master=master,
            upstox_token=settings.UPSTOX_ACCESS_TOKEN,
            trading_date=args.trading_date,
            permission_basis=args.permission_basis,
            count=args.count,
            seed=args.seed,
        )
    except (httpx.HTTPError, OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error(f"refusing to overwrite existing manifest: {args.output}")
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(case, sort_keys=True) + "\n" for case in cases),
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(json.dumps({"cases": len(cases), "output": str(args.output)}, indent=2))
    return 0


def validate_cases(
    cases: list[dict[str, Any]], *, expected_count: int = 150
) -> list[str]:
    """Fail closed on incomplete provenance, duplicate keys, or missing gold."""
    errors: list[str] = []
    if len(cases) != expected_count:
        errors.append(f"expected {expected_count} cases, found {len(cases)}")
    case_ids = [str(case.get("case_id", "")) for case in cases]
    instrument_keys = [str(case.get("instrument_key", "")) for case in cases]
    if any(not value for value in case_ids) or len(set(case_ids)) != len(case_ids):
        errors.append("case_id must be present and unique")
    if any(not value for value in instrument_keys):
        errors.append("instrument_key must be present")
    if len(set(instrument_keys)) != len(instrument_keys):
        errors.append("instrument_key must be unique")
    for case in cases:
        case_id = str(case.get("case_id", ""))
        if not isinstance(case.get("query"), str) or not case["query"].strip():
            errors.append(f"{case_id}: query is required")
        if not _HASH.fullmatch(str(case.get("snapshot_id", ""))):
            errors.append(f"{case_id}: snapshot_id must be a SHA-256 hash")
        for field in ("source_url", "permission_basis"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                errors.append(f"{case_id}: {field} is required")
        if case.get("usage_permission") != "approved":
            errors.append(f"{case_id}: usage_permission must be approved")
        try:
            datetime.fromisoformat(str(case.get("retrieved_at", "")))
        except ValueError:
            errors.append(f"{case_id}: retrieved_at must be an ISO timestamp")
        outcome = case.get("expected_outcome")
        gold = case.get("gold_numbers")
        if outcome not in {"answer", "evidence_gap"}:
            errors.append(f"{case_id}: invalid expected_outcome")
        if not isinstance(gold, dict):
            errors.append(f"{case_id}: gold_numbers must be an object")
        elif outcome == "answer":
            close = gold.get("close")
            if (
                not isinstance(close, (int, float))
                or isinstance(close, bool)
                or not math.isfinite(close)
            ):
                errors.append(f"{case_id}: answer case requires gold_numbers.close")
        elif outcome == "evidence_gap" and gold:
            errors.append(f"{case_id}: evidence_gap case must not have gold numbers")
        key = case.get("instrument_key")
        if not isinstance(key, str) or not key.startswith("NSE_EQ|"):
            errors.append(f"{case_id}: instrument_key must be an NSE_EQ key")
    return errors


def validate_manifest_file(path: Path, archive_root: Path) -> list[str]:
    cases = []
    try:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                return [f"line {line_number}: expected a JSON object"]
            cases.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        return [str(exc)]
    errors = validate_cases(cases, expected_count=len(cases))
    if not errors:
        errors.extend(validate_archive_cases(cases, archive_root))
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
