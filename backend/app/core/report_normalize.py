"""Deterministic, fail-closed pre-repair normalisation of model report output.

Fixes only mechanical problems whose correct fix is unambiguous so that fewer
runs need an LLM repair round. Nothing here invents evidence: a fix is applied
only when exactly one candidate exists, and anything ambiguous or unmatched is
left untouched so the unchanged validator still fails and triggers a repair.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

from app.core.agent_loop.publication import (
    _FACT_MARKER,
    _NUMBER,
    EvidenceFact,
    _format_fact_value,
    _source_records,
)

_FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*[ \t]*\r?\n(.*?)\r?\n?```\s*$", re.DOTALL)
_PLAIN_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)%?$")
_TOKEN = re.compile(r"[a-z]+")
_CONTEXT_CHARS = 80


@dataclass(frozen=True)
class NormalizationChange:
    """One kind of mechanical fix and how many times it was applied."""

    rule: str
    count: int


def _alnum(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _strip_trailing_commas(text: str) -> str:
    """Remove commas directly before a closing bracket, outside JSON strings."""
    out: list[str] = []
    in_string = escaped = False
    for index, char in enumerate(text):
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == ",":
            rest = text[index + 1 :].lstrip()
            if rest[:1] in {"}", "]"}:
                continue
        out.append(char)
    return "".join(out)


def _loads_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _extract_json(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    """Return (object, rule) tolerating fences, surrounding prose, trailing commas."""
    direct = _loads_object(raw)
    if direct is not None:
        return direct, None
    fence = _FENCE.match(raw)
    candidates: list[tuple[str, str]] = []
    if fence:
        candidates.append((fence.group(1), "json_code_fence"))
    start = raw.find("{")
    if start >= 0:
        try:
            _, end = json.JSONDecoder().raw_decode(raw, start)
            if "{" not in raw[end:]:
                candidates.append((raw[start:end], "json_surrounding_prose"))
        except ValueError:
            end = raw.rfind("}") + 1
            # Single object whose only defect may be a trailing comma.
            if end > start and raw.count("{", 0, start) == 0:
                candidates.append((raw[start:end], "json_surrounding_prose"))
    for text, rule in candidates:
        parsed = _loads_object(text)
        if parsed is not None:
            return parsed, rule
        parsed = _loads_object(_strip_trailing_commas(text))
        if parsed is not None:
            whole = rule == "json_surrounding_prose" and text.strip() == raw.strip()
            return parsed, "json_trailing_comma" if whole else rule
    parsed = _loads_object(_strip_trailing_commas(raw))
    if parsed is not None:
        return parsed, "json_trailing_comma"
    return None, None


def _unique(options: set[str]) -> str | None:
    return next(iter(options)) if len(options) == 1 else None


def _metric_tokens(fact: EvidenceFact) -> set[str]:
    field = fact.fact_id.rsplit(".", 1)[-1].rsplit(":", 1)[-1]
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", field).casefold()
    return {token for token in _TOKEN.findall(spaced) if len(token) >= 3}


def normalize_report(
    raw: str,
    evidence: dict[str, EvidenceFact],
    sources: dict[str, dict[str, str]] | None = None,
) -> tuple[str, list[NormalizationChange]]:
    """Return (normalised_text, changes); text is `raw` itself when nothing changed."""
    if not isinstance(raw, str):
        return raw, []
    obj, json_rule = _extract_json(raw)
    if obj is None:
        return raw, []
    counts: dict[str, int] = {}
    if json_rule:
        counts[json_rule] = 1

    def bump(rule: str, amount: int = 1) -> None:
        counts[rule] = counts.get(rule, 0) + amount

    claims = (
        [c for c in obj.get("claims", []) if isinstance(c, dict)]
        if isinstance(obj.get("claims"), list)
        else []
    )
    citations = (
        [c for c in obj.get("citations", []) if isinstance(c, dict)]
        if (isinstance(obj.get("citations"), list))
        else []
    )

    # --- citations: source ids -------------------------------------------------
    records = dict(_source_records(evidence))
    source_records: dict[str, Any] = {**records, **(sources or {})}
    aliases: dict[str, set[str]] = {}
    for source_id, record in source_records.items():
        names: list[str] = [source_id]
        if isinstance(record, dict):
            names += [str(record.get("name") or ""), str(record.get("url") or "")]
        else:
            names.append(record.source_url or "")
        for name in names:
            key = _alnum(name)
            if key:
                aliases.setdefault(key, set()).add(source_id)
    for citation in citations:
        cited = citation.get("source_id")
        if not isinstance(cited, str) or cited in source_records:
            continue
        match = _unique(aliases.get(_alnum(cited), set()))
        if match is not None:
            citation["source_id"] = match
            bump("citation_source_id")

    # --- claims: evidence_refs -> citation ids ---------------------------------
    citation_ids = {
        c["citation_id"] for c in citations if isinstance(c.get("citation_id"), str)
    }
    by_key: dict[str, set[str]] = {}
    for cid in citation_ids:
        by_key.setdefault(_alnum(cid), set()).add(cid)
    by_source: dict[str, set[str]] = {}
    for citation in citations:
        cid, sid = citation.get("citation_id"), citation.get("source_id")
        if isinstance(cid, str) and isinstance(sid, str):
            by_source.setdefault(sid, set()).add(cid)
    for claim in claims:
        refs = claim.get("evidence_refs")
        if not isinstance(refs, list):
            continue
        for index, ref in enumerate(refs):
            if not isinstance(ref, str) or ref in citation_ids:
                continue
            match = _unique(by_key.get(_alnum(ref), set()))
            if match is None:
                sources_hit = aliases.get(_alnum(ref), set())
                source = _unique(sources_hit)
                if source is not None:
                    match = _unique(by_source.get(source, set()))
            if match is not None:
                refs[index] = match
                bump("claim_evidence_ref")

    # --- fact ids (numeric_refs and markers) -----------------------------------
    fact_keys: dict[str, set[str]] = {}
    for fact_id in evidence:
        fact_keys.setdefault(fact_id.strip().casefold(), set()).add(fact_id)

    def fix_fact_id(fact_id: str) -> str | None:
        if fact_id in evidence:
            return None
        return _unique(fact_keys.get(fact_id.strip().casefold(), set()))

    def fix_markers(text: str) -> str:
        def repl(match: re.Match[str]) -> str:
            fixed = fix_fact_id(match.group(1))
            if fixed is None:
                return match.group(0)
            bump("fact_marker_id")
            return f"[[fact:{fixed}]]"

        return _FACT_MARKER.sub(repl, text)

    for claim in claims:
        refs = claim.get("numeric_refs")
        if isinstance(refs, list):
            for index, ref in enumerate(refs):
                if isinstance(ref, str):
                    fixed = fix_fact_id(ref)
                    if fixed is not None:
                        refs[index] = fixed
                        bump("numeric_ref_id")
        if isinstance(claim.get("text"), str):
            claim["text"] = fix_markers(claim["text"])
    for key in ("executive_summary", "detailed_analysis", "final_view"):
        if isinstance(obj.get(key), str):
            obj[key] = fix_markers(obj[key])
    for key in ("key_drivers", "risks"):
        if isinstance(obj.get(key), list):
            obj[key] = [fix_markers(i) if isinstance(i, str) else i for i in obj[key]]

    # --- numeric links ---------------------------------------------------------
    def referenced() -> set[str]:
        return {
            r
            for c in claims
            if isinstance(c.get("numeric_refs"), list)
            for r in c["numeric_refs"]
            if isinstance(r, str)
        }

    # Marker already placed in exactly one claim text, but never referenced.
    claim_texts = [c["text"] for c in claims if isinstance(c.get("text"), str)]
    for fact_id in sorted(
        {m for t in claim_texts for m in _FACT_MARKER.findall(t)} - referenced()
    ):
        if fact_id not in evidence:
            continue
        owners = [
            c
            for c in claims
            if isinstance(c.get("text"), str)
            and fact_id in _FACT_MARKER.findall(c["text"])
        ]
        if len(owners) == 1:
            refs = owners[0].get("numeric_refs")
            if refs is None:
                refs = owners[0]["numeric_refs"] = []
            if isinstance(refs, list):
                refs.append(fact_id)
                bump("numeric_ref_link")

    numeric_facts = [f for f in evidence.values() if not isinstance(f.value, str)]

    def link_number(literal: str, start: int, end: int, text: str) -> str | None:
        if not _PLAIN_NUMBER.match(literal):
            return None
        number = float(literal.rstrip("%"))
        candidates = [
            f
            for f in numeric_facts
            if math.isclose(float(f.value), number, rel_tol=1e-3, abs_tol=1e-9)
        ]
        if len(candidates) != 1:
            return None
        fact = candidates[0]
        if literal.endswith("%") != _format_fact_value(fact).endswith("%"):
            return None
        context = text[max(0, start - _CONTEXT_CHARS) : end + _CONTEXT_CHARS].casefold()
        if not any(token in context for token in _metric_tokens(fact)):
            return None
        return fact.fact_id

    def link_text(text: str, claim: dict[str, Any] | None) -> str:
        parts: list[str] = []
        last = 0
        for marker in _FACT_MARKER.finditer(text):
            parts.append(text[last : marker.start()])
            parts.append(marker.group(0))
            last = marker.end()
        parts.append(text[last:])
        # Offsets for context are relative to each marker-free segment's full text.
        out: list[str] = []
        offset = 0
        for segment in parts:
            if _FACT_MARKER.fullmatch(segment):
                out.append(segment)
                offset += len(segment)
                continue
            pieces: list[str] = []
            pos = 0
            for match in _NUMBER.finditer(segment):
                fact_id = link_number(
                    match.group(0), offset + match.start(), offset + match.end(), text
                )
                if fact_id is None:
                    continue
                if claim is not None:
                    refs = claim.get("numeric_refs")
                    if refs is None:
                        refs = claim["numeric_refs"] = []
                    if not isinstance(refs, list):
                        continue
                    if fact_id not in refs:
                        refs.append(fact_id)
                elif fact_id not in referenced():
                    continue
                pieces.append(segment[pos : match.start()])
                pieces.append(f"[[fact:{fact_id}]]")
                pos = match.end()
                bump("numeric_value_link")
            pieces.append(segment[pos:])
            out.append("".join(pieces))
            offset += len(segment)
        return "".join(out)

    for claim in claims:
        if isinstance(claim.get("text"), str):
            claim["text"] = link_text(claim["text"], claim)
    for key in ("executive_summary", "detailed_analysis", "final_view"):
        if isinstance(obj.get(key), str):
            obj[key] = link_text(obj[key], None)
    for key in ("key_drivers", "risks"):
        if isinstance(obj.get(key), list):
            obj[key] = [
                link_text(i, None) if isinstance(i, str) else i for i in obj[key]
            ]

    if not counts:
        return raw, []
    changes = [NormalizationChange(rule, n) for rule, n in sorted(counts.items())]
    return json.dumps(obj, ensure_ascii=False), changes
