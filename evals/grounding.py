"""Deterministic numeric grounding score for answers against gold numbers.

No model calls. Numeric claims in an answer are extracted with a regex, then
compared with the case's gold numbers (and optional evidence facts):

* matched       - the claim equals a gold/evidence value within tolerance
* contradicted  - the claim is explicitly labelled (e.g. "close", "volume") as
                  a gold quantity but differs beyond tolerance
* unverifiable  - the claim has no label and matches no known value

This checks numbers only. It does not judge wording, reasoning, or citations.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

_NUMBER = re.compile(
    r"(?<![\w.])(?P<sign>[-+−])?\s?(?:₹|Rs\.?\s?|INR\s?)?"
    r"(?P<num>\d[\d,]*(?:\.\d+)?)\s?(?P<unit>%|crore|lakh|million|billion|k\b)?",
    re.IGNORECASE,
)
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?|\d{1,2}:\d{2}")
_COUNT_AFTER = re.compile(
    r"(rows?|days?|trading|months?|weeks?|years?|data points?|candles?|bars?|periods?)\b"
)
_COUNT_BEFORE = re.compile(r"(row count|rows|period|lookback|last|window)\W*$")
_UNIT_SCALE = {"crore": 1e7, "lakh": 1e5, "million": 1e6, "billion": 1e9, "k": 1e3}

#: Keywords that tie a nearby number to a gold quantity (matched in order).
LABELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "previous_close",
        ("previous close", "prior close", "previous closing", "prev close"),
    ),
    ("avg_volume_20", ("average volume", "avg volume", "20-day volume")),
    ("high_52w", ("52-week high", "52 week high", "52w high", "year high")),
    ("low_52w", ("52-week low", "52 week low", "52w low", "year low")),
    ("day_change_pct", ("daily change", "day change", "change of", "% change")),
    ("macd_signal", ("macd signal", "signal line")),
    ("macd_hist", ("macd histogram", "histogram")),
    ("macd", ("macd",)),
    ("rsi_14", ("rsi",)),
    ("sma_20", ("sma", "simple moving average", "20-day average", "20-day moving")),
    ("ema_20", ("ema", "exponential moving average")),
    ("volume", ("volume", "shares traded")),
    ("high", ("high", "upper end")),
    ("low", ("low", "lower end")),
    ("close", ("close", "closing", "closed", "last price")),
)


def _within(claim: float, expected: float, rel: float, absolute: float) -> bool:
    return abs(claim - expected) <= max(absolute, abs(expected) * rel)


def _facts(
    source: Mapping[str, Any] | None, specs: Mapping[str, Any] | None
) -> dict[str, tuple[float, float, float]]:
    """name -> (value, relative tolerance, absolute tolerance)."""
    facts: dict[str, tuple[float, float, float]] = {}
    for name, value in (source or {}).items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        spec = (specs or {}).get(name) or {}
        facts[name] = (
            float(value),
            float(spec.get("tolerance_rel", 0.005)),
            float(spec.get("tolerance_abs", 0.01)),
        )
    return facts


def extract_numbers(text: str) -> list[dict[str, Any]]:
    """Return numeric claims with value, unit and the text before/after them."""
    masked = _DATE.sub(lambda m: " " * len(m.group(0)), text)
    claims: list[dict[str, Any]] = []
    for match in _NUMBER.finditer(masked):
        raw = match.group("num").replace(",", "")
        value = float(raw)
        unit = (match.group("unit") or "").lower()
        if match.group("sign") in {"-", "−"}:
            value = -value
        trailing = masked[match.end("num") : match.end("num") + 12].lower().lstrip()
        if not unit and masked[match.end("num") : match.end("num") + 1].isalpha():
            continue  # part of an identifier or hash, e.g. 54a547c4
        if _COUNT_AFTER.match(trailing) or _COUNT_BEFORE.search(
            masked[max(0, match.start() - 14) : match.start()].lower()
        ):
            continue  # row/day counts and lookback windows are not market claims
        if unit in _UNIT_SCALE:
            value *= _UNIT_SCALE[unit]
        elif not unit and "." not in raw and 1900 <= value <= 2100:
            continue  # bare year
        start = max(0, match.start() - 45)
        before = re.split(r"[.;\n]\s|\n", masked[start : match.start()])[-1].lower()
        after = masked[match.end() : match.end() + 14].lower()
        claims.append(
            {
                "text": match.group(0).strip(),
                "value": value,
                "percent": unit == "%",
                "before": before,
                "after": after,
            }
        )
    return claims


def _label(claim: Mapping[str, Any], facts: Mapping[str, Any]) -> str | None:
    """Label from the phrase just before the number, else a trailing keyword."""
    before = claim["before"][-30:]
    after = claim["after"].lstrip(" ,:)(-")
    for name, keywords in LABELS:
        if name in facts and any(
            keyword in before or after.startswith(keyword) for keyword in keywords
        ):
            return name
    return None


def score_answer(
    answer: str,
    gold_numbers: Mapping[str, Any] | None,
    *,
    gold_number_specs: Mapping[str, Any] | None = None,
    evidence_facts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify each numeric claim in ``answer`` and compute a grounding score."""
    gold = _facts(gold_numbers, gold_number_specs)
    evidence = _facts(evidence_facts, None)
    known = {**evidence, **gold}
    matched: list[dict[str, Any]] = []
    contradicted: list[dict[str, Any]] = []
    unverifiable: list[dict[str, Any]] = []
    for claim in extract_numbers(answer):
        record = {"text": claim["text"], "value": claim["value"]}
        label = _label(claim, known)
        if label is not None:
            value, rel, absolute = known[label]
            if _within(claim["value"], value, rel, absolute):
                matched.append({**record, "gold": label})
            else:
                contradicted.append({**record, "gold": label, "expected": value})
            continue
        hit = next(
            (
                name
                for name, (value, rel, absolute) in known.items()
                if _within(claim["value"], value, rel, absolute)
            ),
            None,
        )
        if hit is not None:
            matched.append({**record, "gold": hit})
        else:
            unverifiable.append(record)
    total = len(matched) + len(contradicted) + len(unverifiable)
    gold_found = {item["gold"] for item in matched if item["gold"] in gold}
    return {
        "matched": matched,
        "contradicted": contradicted,
        "unverifiable": unverifiable,
        "claims": total,
        "score": len(matched) / total if total else None,
        "gold_coverage": len(gold_found) / len(gold) if gold else None,
        "has_contradiction": bool(contradicted),
    }


def _success(status: Any) -> bool:
    return status in {"success", "completed"}


def grounding_report(
    cases: Iterable[Mapping[str, Any]],
    results: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate grounding next to terminal success. ``results`` is keyed by case id.

    Only cases that have gold numbers and an answer text are scored; others are
    counted as ``not_scored`` rather than silently passing.
    """
    per_case: list[dict[str, Any]] = []
    terminal_total = terminal_success = 0
    not_scored = 0
    for case in cases:
        case_id = str(case.get("id") or case.get("case_id"))
        result = results.get(case_id)
        if result is None:
            continue
        terminal_total += 1
        terminal_success += _success(result.get("terminal_status"))
        gold = case.get("gold_numbers")
        text = result.get("report") or result.get("answer")
        if not gold or not isinstance(text, str) or not text.strip():
            not_scored += 1
            continue
        scored = score_answer(
            text, gold, gold_number_specs=case.get("gold_number_specs")
        )
        per_case.append(
            {
                "case_id": case_id,
                "terminal_status": result.get("terminal_status"),
                "claims": scored["claims"],
                "matched": len(scored["matched"]),
                "contradicted": len(scored["contradicted"]),
                "unverifiable": len(scored["unverifiable"]),
                "score": scored["score"],
                "gold_coverage": scored["gold_coverage"],
            }
        )
    claims = sum(item["claims"] for item in per_case)
    matched = sum(item["matched"] for item in per_case)
    contradicted = sum(item["contradicted"] for item in per_case)
    scored_cases = [item for item in per_case if item["claims"]]
    return {
        "terminal_success": {
            "success": terminal_success,
            "total": terminal_total,
            "rate": terminal_success / terminal_total if terminal_total else None,
        },
        "grounding": {
            "cases_scored": len(per_case),
            "cases_not_scored": not_scored,
            "claims": claims,
            "matched": matched,
            "contradicted": contradicted,
            "unverifiable": claims - matched - contradicted,
            "claim_score": matched / claims if claims else None,
            "cases_with_contradiction": sum(
                1 for item in per_case if item["contradicted"]
            ),
            "mean_case_score": (
                sum(item["score"] for item in scored_cases) / len(scored_cases)
                if scored_cases
                else None
            ),
            "gold_coverage": (
                sum(item["gold_coverage"] or 0.0 for item in per_case) / len(per_case)
                if per_case
                else None
            ),
        },
        "per_case": per_case,
        "notes": [
            "Numeric grounding only; no semantic or LLM-judge scoring.",
            "Terminal success measures run completion, not answer correctness.",
        ],
    }


def load_results(path: Path) -> dict[str, dict[str, Any]]:
    """Load results from a JSONL file or a directory of per-case artifact JSON."""
    records: list[dict[str, Any]] = []
    if path.is_dir():
        records = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(path.glob("*.json"))
        ]
    else:
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return {str(r.get("case_id") or r.get("id")): r for r in records}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline numeric grounding score.")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument(
        "--results", type=Path, required=True, help="JSONL or artifact dir"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    cases = [
        json.loads(line)
        for line in args.cases.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = grounding_report(cases, load_results(args.results))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    summary = {k: report[k] for k in ("terminal_success", "grounding")}
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
