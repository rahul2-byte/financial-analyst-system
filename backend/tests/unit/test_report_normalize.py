import json
from datetime import UTC, datetime
from typing import Any

import pytest
from app.core.agent_loop.publication import (
    EvidenceFact,
    PublicationError,
    parse_report_draft,
    publish_report,
)
from app.core.report_normalize import normalize_report

_SRC = "source:yfinance"


def _fact(fact_id: str, value: float, source: str = _SRC, unit: str = "provider_value"):
    return EvidenceFact(
        fact_id=fact_id,
        value=value,
        unit=unit,
        source_id=source,
        instrument="ABC.NS",
        observed_at=datetime(2026, 9, 18, tzinfo=UTC),
        quality_status="verified",
        source_url=f"https://example.test/{source}",
    )


def _evidence() -> dict[str, EvidenceFact]:
    facts = [
        _fact("price.latest", 123.4),
        _fact("ratios.pe_ratio", 22.7),
        _fact("returns.period_return_pct", 12.5),
        _fact("ratios.other_pe", 22.7),
    ]
    return {f.fact_id: f for f in facts}


def _report(**over: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "executive_summary": "Summary.",
        "key_drivers": ["Driver."],
        "detailed_analysis": "Analysis.",
        "risks": ["Risk."],
        "final_view": "View.",
        "claims": [
            {
                "claim_id": "c1",
                "text": "Latest price is [[fact:price.latest]].",
                "importance": "major",
                "evidence_refs": ["cit-1"],
                "numeric_refs": ["price.latest"],
            }
        ],
        "citations": [{"citation_id": "cit-1", "source_id": _SRC}],
    }
    value.update(over)
    return value


def _norm(obj: Any, ev=None, sources=None):
    raw = obj if isinstance(obj, str) else json.dumps(obj)
    return normalize_report(raw, ev or _evidence(), sources)


def _publishes(text: str, ev=None) -> bool:
    try:
        publish_report(parse_report_draft(text), ev or _evidence())
    except PublicationError:
        return False
    return True


def _fails(text: str) -> bool:
    return not _publishes(text)


def test_valid_report_is_byte_identical() -> None:
    raw = json.dumps(_report(), indent=2)
    out, changes = normalize_report(raw, _evidence())
    assert out is raw and changes == []
    assert _publishes(out)


def test_code_fence_and_prose_and_trailing_comma() -> None:
    body = json.dumps(_report())
    for raw, rule in [
        (f"```json\n{body}\n```", "json_code_fence"),
        (f"Here is the report:\n{body}\nHope it helps.", "json_surrounding_prose"),
        (body[:-1] + ",}", "json_trailing_comma"),
        (f"```json\n{body[:-1]},}}\n```", "json_code_fence"),
    ]:
        out, changes = normalize_report(raw, _evidence())
        assert [c.rule for c in changes] == [rule], raw
        assert _publishes(out)


def test_json_not_guessed() -> None:
    for raw in ["not json", '{"a": 1} and {"b": 2}', '{"claims": [', "[1, 2]"]:
        assert normalize_report(raw, _evidence()) == (raw, [])
    missing = json.dumps({k: v for k, v in _report().items() if k != "risks"})
    out, _ = normalize_report(f"```\n{missing}\n```", _evidence())
    assert _fails(out)


def test_trailing_comma_inside_string_preserved() -> None:
    rep = _report(final_view='Keep ",}" intact.')
    raw = json.dumps(rep)[:-1] + ",}"
    out, _ = normalize_report(raw, _evidence())
    assert json.loads(out)["final_view"] == 'Keep ",}" intact.'


def test_citation_source_id_formatting_fixed() -> None:
    rep = _report(
        citations=[{"citation_id": "cit-1", "source_id": " SOURCE_YFINANCE "}]
    )
    raw = json.dumps(rep)
    assert _fails(raw)
    out, changes = normalize_report(raw, _evidence())
    assert ("citation_source_id", 1) in [(c.rule, c.count) for c in changes]
    assert _publishes(out)


def test_citation_source_id_by_url_or_name() -> None:
    sources = {"s1": {"name": "Exchange News", "url": "https://n.test/a"}}
    ev = _evidence()
    for ref in ("https://n.test/a", "exchange news"):
        rep = _report(citations=[{"citation_id": "cit-1", "source_id": ref}])
        out, changes = normalize_report(json.dumps(rep), ev, sources)
        assert json.loads(out)["citations"][0]["source_id"] == "s1"
        assert changes


def test_ambiguous_or_unmatched_citation_left_alone() -> None:
    sources = {"src-1": {"name": "a", "url": "u"}, "SRC_1": {"name": "b", "url": "v"}}
    rep = _report(citations=[{"citation_id": "cit-1", "source_id": "Src 1"}])
    raw = json.dumps(rep)
    assert normalize_report(raw, _evidence(), sources) == (raw, [])
    rep = _report(citations=[{"citation_id": "cit-1", "source_id": "unknown"}])
    raw = json.dumps(rep)
    assert normalize_report(raw, _evidence()) == (raw, [])
    assert _fails(raw)


def test_evidence_ref_formatting_fixed_and_ambiguous_left() -> None:
    rep = _report()
    rep["claims"][0]["evidence_refs"] = [" CIT_1 "]
    out, changes = normalize_report(json.dumps(rep), _evidence())
    assert changes and _publishes(out)
    rep["citations"].append({"citation_id": "CIT_1", "source_id": _SRC})
    rep["claims"][0]["evidence_refs"] = ["cit 1"]
    raw = json.dumps(rep)
    out, _ = normalize_report(raw, _evidence())
    assert json.loads(out)["claims"][0]["evidence_refs"] == ["cit 1"]
    assert _fails(out)


def test_never_attaches_citation_to_unsupported_claim() -> None:
    rep = _report()
    rep["claims"][0]["evidence_refs"] = []
    out, changes = normalize_report(json.dumps(rep), _evidence())
    assert changes == []
    assert _fails(out)
    rep["claims"][0]["evidence_refs"] = ["totally-unrelated"]
    out, _ = normalize_report(json.dumps(rep), _evidence())
    assert json.loads(out)["claims"][0]["evidence_refs"] == ["totally-unrelated"]
    assert _fails(out)


def test_fact_id_case_fixed() -> None:
    rep = _report()
    rep["claims"][0]["numeric_refs"] = ["Price.Latest"]
    rep["claims"][0]["text"] = "Latest price is [[fact:PRICE.latest]]."
    out, changes = normalize_report(json.dumps(rep), _evidence())
    assert {c.rule for c in changes} == {"numeric_ref_id", "fact_marker_id"}
    assert _publishes(out)


def test_unreferenced_marker_linked_when_single_owner() -> None:
    rep = _report()
    rep["claims"][0]["numeric_refs"] = []
    raw = json.dumps(rep)
    assert _fails(raw)
    out, changes = normalize_report(raw, _evidence())
    assert [c.rule for c in changes] == ["numeric_ref_link"]
    assert _publishes(out)


def test_unreferenced_marker_ambiguous_owner_left() -> None:
    rep = _report()
    rep["claims"][0]["numeric_refs"] = []
    rep["claims"].append({**rep["claims"][0], "claim_id": "c2"})
    out, changes = normalize_report(json.dumps(rep), _evidence())
    assert changes == [] and _fails(out)


def test_bare_number_linked_when_unique_and_metric_matches() -> None:
    rep = _report()
    rep["claims"][0]["text"] = "Latest price is 123.4 today."
    rep["claims"][0]["numeric_refs"] = []
    raw = json.dumps(rep)
    assert _fails(raw)
    out, changes = normalize_report(raw, _evidence())
    assert [c.rule for c in changes] == ["numeric_value_link"]
    assert _publishes(out)


def test_bare_percent_linked_and_summary_linked_only_if_referenced() -> None:
    rep = _report()
    rep["claims"][0]["text"] = "Period return was 12.5% recently."
    rep["claims"][0]["numeric_refs"] = []
    rep["executive_summary"] = "The period return of 12.5% stands out."
    out, _ = normalize_report(json.dumps(rep), _evidence())
    assert _publishes(out)
    # Summary-only number whose fact no claim references stays unbound.
    rep = _report(executive_summary="The period return of 12.5% stands out.")
    out, changes = normalize_report(json.dumps(rep), _evidence())
    assert changes == [] and _fails(out)


def test_duplicate_value_or_wrong_metric_not_linked() -> None:
    rep = _report()
    rep["claims"][0]["text"] = "PE ratio is 22.7 now."  # two facts share 22.7
    out, changes = normalize_report(json.dumps(rep), _evidence())
    assert changes == [] and _fails(out)
    rep["claims"][0]["text"] = "Headcount grew by 123.4 now."  # no metric match
    out, changes = normalize_report(json.dumps(rep), _evidence())
    assert changes == [] and _fails(out)
    rep["claims"][0]["text"] = "Period return was 12.5 recently."  # percent mismatch
    out, changes = normalize_report(json.dumps(rep), _evidence())
    assert changes == [] and _fails(out)
    rep["claims"][0]["text"] = "Latest price is 999 today."  # no such fact
    out, changes = normalize_report(json.dumps(rep), _evidence())
    assert changes == [] and _fails(out)


def test_linked_fact_without_cited_source_still_fails() -> None:
    ev = _evidence()
    ev["price.latest"] = _fact("price.latest", 123.4, source="source:other")
    rep = _report()
    rep["claims"][0]["text"] = "Latest price is 123.4 today."
    rep["claims"][0]["numeric_refs"] = []
    out, changes = normalize_report(json.dumps(rep), ev)
    assert changes
    assert _fails(out) or not _publishes(out, ev)


@pytest.mark.parametrize("raw", ["", "   ", "{}"])
def test_degenerate_inputs_unchanged(raw: str) -> None:
    assert normalize_report(raw, _evidence()) == (raw, [])
