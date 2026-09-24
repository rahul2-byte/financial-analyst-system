import json
from datetime import UTC, datetime

import pytest
from app.core.agent_loop.publication import (
    EvidenceFact,
    LookupAnswerV1,
    PublicationError,
    ReportDraft,
    lookup_repair_instruction,
    parse_lookup_answer,
    parse_report_draft,
    publish_lookup_answer,
    publish_report,
    report_repair_instruction,
    report_validation_fallback,
    unreferenced_fact_markers,
)


def _evidence() -> dict[str, EvidenceFact]:
    return {
        "price.latest": EvidenceFact(
            fact_id="price.latest",
            value=123.4,
            unit="INR",
            source_id="source:yfinance",
            instrument="ABC.NS",
            observed_at=datetime(2026, 9, 18, tzinfo=UTC),
            quality_status="verified",
            source_url="https://example.test/price",
        )
    }


def _draft(**overrides: object) -> ReportDraft:
    values: dict[str, object] = {
        "executive_summary": "Evidence-backed summary.",
        "key_drivers": ["Demand remains a driver."],
        "detailed_analysis": "The latest price is [[fact:price.latest]].",
        "risks": ["Execution risk remains."],
        "final_view": "Review the evidence before acting.",
        "claims": [
            {
                "claim_id": "claim-1",
                "text": "The latest price is [[fact:price.latest]].",
                "importance": "major",
                "evidence_refs": ["citation-1"],
                "numeric_refs": ["price.latest"],
            }
        ],
        "citations": [{"citation_id": "citation-1", "source_id": "source:yfinance"}],
    }
    values.update(overrides)
    return ReportDraft.model_validate(values)


def test_publish_report_renders_only_verified_numeric_facts() -> None:
    result = publish_report(_draft(), _evidence())

    assert "123.4 INR" in result
    assert "[[fact:" not in result


def test_report_repair_instruction_includes_verified_fact_values() -> None:
    prompt = report_repair_instruction(_evidence(), ("numeric_fact_missing",))
    lookup_prompt = lookup_repair_instruction(_evidence(), ("numeric_fact_missing",))

    assert "price.latest = 123.4 INR" in prompt
    assert "price.latest = 123.4 INR" in lookup_prompt


def test_report_repair_instruction_names_unreferenced_fact_ids() -> None:
    draft = _draft(
        detailed_analysis="The source time is [[fact:source.observed_at]]."
    )
    missing = unreferenced_fact_markers(draft)
    prompt = report_repair_instruction(
        _evidence(),
        ("numeric_fact_reference_missing",),
        unreferenced_fact_ids=missing,
    )

    assert missing == ("source.observed_at",)
    assert "Unreferenced fact IDs: source.observed_at" in prompt


def test_parse_report_normalizes_bracketed_numeric_refs_before_publication() -> None:
    payload = _draft().model_dump(mode="json")
    payload["claims"][0]["numeric_refs"] = ["[[fact:price.latest]]"]

    draft = parse_report_draft(json.dumps(payload))

    assert draft.claims[0].numeric_refs == ["price.latest"]
    assert "123.4 INR" in publish_report(draft, _evidence())


def test_publish_report_requires_every_fact_marker_in_numeric_refs() -> None:
    payload = _draft().model_dump(mode="json")
    payload["claims"][0]["numeric_refs"] = []

    with pytest.raises(PublicationError, match="numeric_fact_reference_missing"):
        publish_report(ReportDraft.model_validate(payload), _evidence())


def test_publish_report_formats_provider_values_by_metric() -> None:
    evidence = {
        "historical_prices:data.period_return_pct": EvidenceFact(
            fact_id="historical_prices:data.period_return_pct",
            value=-25.1715,
            unit="provider_value",
            source_id="source:yfinance",
            instrument="ABC.NS",
            observed_at=datetime(2026, 9, 18, tzinfo=UTC),
            quality_status="verified",
            source_url="https://example.test/history",
        ),
        "historical_prices:data.Volume": EvidenceFact(
            fact_id="historical_prices:data.Volume",
            value=39400710,
            unit="provider_value",
            source_id="source:yfinance",
            instrument="ABC.NS",
            observed_at=datetime(2026, 9, 18, tzinfo=UTC),
            quality_status="verified",
            source_url="https://example.test/history",
        ),
    }
    draft = _draft(
        detailed_analysis=(
            "Return [[fact:historical_prices:data.period_return_pct]] with volume "
            "[[fact:historical_prices:data.Volume]]."
        ),
        claims=[
            {
                "claim_id": "claim-1",
                "text": (
                    "Return [[fact:historical_prices:data.period_return_pct]] with volume "
                    "[[fact:historical_prices:data.Volume]]."
                ),
                "importance": "major",
                "evidence_refs": ["citation-1"],
                "numeric_refs": [
                    "historical_prices:data.period_return_pct",
                    "historical_prices:data.Volume",
                ],
            }
        ],
    )

    result = publish_report(draft, evidence)

    assert "-25.17%" in result
    assert "39,400,710" in result
    assert "provider_value" not in result


def test_publish_report_renders_verified_timestamp_fact() -> None:
    timestamp = EvidenceFact(
        fact_id="history:data.0.timestamp",
        value="2026-09-22T00:00:00+05:30",
        unit="provider_timestamp",
        source_id="source:yfinance",
        instrument="ABC.NS",
        observed_at=datetime(2026, 9, 23, tzinfo=UTC),
        quality_status="verified",
        source_url="https://example.test/history",
    )
    draft = _draft(
        detailed_analysis="Observed at [[fact:history:data.0.timestamp]].",
        claims=[
            {
                "claim_id": "claim-1",
                "text": "Observed at [[fact:history:data.0.timestamp]].",
                "importance": "major",
                "evidence_refs": ["citation-1"],
                "numeric_refs": ["history:data.0.timestamp"],
            }
        ],
    )

    result = publish_report(draft, {timestamp.fact_id: timestamp})

    assert "Observed at 2026-09-22T00:00:00+05:30." in result
    assert "[[fact:" not in result


def test_publish_report_discloses_limited_evidence_and_price_basis() -> None:
    result = publish_report(
        _draft(),
        _evidence(),
        availability={
            "news": {
                "source": "news",
                "status": "unavailable",
                "reason": "provider timeout",
                "evidence_count": 0,
            }
        },
    )

    assert "Evidence status: LIMITED" in result
    assert "News evidence was unavailable" in result


def test_publish_report_renders_claim_references_and_sources() -> None:
    result = publish_report(_draft(), _evidence())

    assert "## Claims and references" in result
    assert "The latest price is 123.4 INR." in result
    assert "citation-1" in result
    assert "## Sources" in result
    assert "source:yfinance" in result
    assert "https://example.test/price" in result
    assert "2026-09-18T00:00:00+00:00" in result


def test_publish_report_accepts_verified_qualitative_source_records() -> None:
    draft = _draft(
        detailed_analysis="The article supports the qualitative claim.",
        claims=[
            {
                "claim_id": "claim-1",
                "text": "The article supports the qualitative claim.",
                "importance": "major",
                "evidence_refs": ["citation-news"],
                "numeric_refs": [],
            }
        ],
        citations=[{"citation_id": "citation-news", "source_id": "news:example.com"}],
    )

    result = publish_report(
        draft,
        {},
        {
            "news:example.com": {
                "name": "example.com",
                "url": "https://example.com/news",
            }
        },
    )

    assert "https://example.com/news" in result


def test_publish_report_rejects_major_claim_from_degraded_source() -> None:
    draft = _draft(
        citations=[{"citation_id": "citation-1", "source_id": "fundamentals"}],
        claims=[
            {
                "claim_id": "claim-1",
                "text": "Profitability is constructive.",
                "importance": "major",
                "evidence_refs": ["citation-1"],
            }
        ],
        detailed_analysis="Profitability is constructive.",
    )

    with pytest.raises(PublicationError, match="degraded_source_claim"):
        publish_report(
            draft,
            {},
            {
                "fundamentals": {
                    "name": "fundamentals",
                    "url": "https://example.test/fundamentals",
                    "quality_status": "degraded",
                }
            },
        )


def test_publish_report_rejects_unsupported_major_claim() -> None:
    draft = _draft(
        claims=[
            {
                "claim_id": "claim-1",
                "text": "Unsupported conclusion.",
                "importance": "major",
            }
        ],
        detailed_analysis="No numeric facts.",
    )

    with pytest.raises(PublicationError, match="major_claim_unsupported"):
        publish_report(draft, _evidence())


def test_publish_report_rejects_unbound_numeric_claim() -> None:
    draft = _draft(
        executive_summary="The return was 12 percent.",
        detailed_analysis="No numeric facts.",
        claims=[
            {
                "claim_id": "claim-1",
                "text": "A supported qualitative claim.",
                "importance": "major",
                "evidence_refs": ["citation-1"],
            }
        ],
    )

    with pytest.raises(PublicationError, match="numeric_claim_unbound"):
        publish_report(draft, _evidence())


def test_publish_report_does_not_treat_digits_in_ticker_as_unbound_numbers() -> None:
    draft = _draft(final_view="HDFCNEXT50 has a verified observation.")

    assert "HDFCNEXT50" in publish_report(draft, _evidence())


def test_publish_report_rejects_numeric_claim_text_without_fact_marker() -> None:
    draft = _draft(
        claims=[
            {
                "claim_id": "claim-1",
                "text": "The return was 100%.",
                "importance": "major",
                "evidence_refs": ["citation-1"],
            }
        ],
        detailed_analysis="No numeric facts.",
    )

    with pytest.raises(PublicationError, match="numeric_claim_unbound"):
        publish_report(draft, _evidence())


def test_publish_report_rejects_guaranteed_return_claim() -> None:
    draft = _draft(
        claims=[
            {
                "claim_id": "claim-1",
                "text": "This stock has a guaranteed return.",
                "importance": "major",
                "evidence_refs": ["citation-1"],
            }
        ],
        detailed_analysis="No numeric facts.",
    )

    with pytest.raises(PublicationError, match="unsafe_guarantee_claim"):
        publish_report(draft, _evidence())


def test_publish_report_rejects_unknown_source() -> None:
    draft = _draft(citations=[{"citation_id": "citation-1", "source_id": "unknown"}])

    with pytest.raises(PublicationError, match="citation_source_missing"):
        publish_report(draft, _evidence())


def test_publish_report_rejects_duplicate_citation_ids() -> None:
    draft = _draft(
        citations=[
            {"citation_id": "citation-1", "source_id": "source:yfinance"},
            {"citation_id": "citation-1", "source_id": "source:yfinance"},
        ]
    )

    with pytest.raises(PublicationError, match="duplicate_citation_id"):
        publish_report(draft, _evidence())


def test_publish_report_rejects_citation_without_source_url() -> None:
    evidence = {
        fact_id: fact.model_copy(update={"source_url": None})
        for fact_id, fact in _evidence().items()
    }

    with pytest.raises(PublicationError, match="citation_source_url_missing"):
        publish_report(_draft(), evidence)


def test_publish_report_rejects_numeric_fact_with_unresolved_source() -> None:
    other_fact = EvidenceFact(
        fact_id="other.latest",
        value=99.0,
        unit="INR",
        source_id="source:other",
        instrument="ABC.NS",
        observed_at=datetime(2026, 9, 18, tzinfo=UTC),
        quality_status="verified",
        source_url="https://example.test/other",
    )
    draft = _draft(
        citations=[{"citation_id": "citation-1", "source_id": "source:other"}]
    )

    with pytest.raises(PublicationError, match="numeric_fact_source_missing"):
        publish_report(draft, {**_evidence(), "other.latest": other_fact})


def test_parse_report_draft_rejects_non_json() -> None:
    with pytest.raises(PublicationError, match="structured_report_invalid"):
        parse_report_draft("plain text report")


def test_parse_report_draft_rejects_fields_outside_declared_schema() -> None:
    payload = _draft().model_dump(mode="json")
    payload["unreviewed_field"] = "must not be silently accepted"

    with pytest.raises(PublicationError, match="structured_report_invalid"):
        parse_report_draft(json.dumps(payload))


def test_lookup_answer_reuses_evidence_and_citation_validation() -> None:
    answer = LookupAnswerV1.model_validate(
        {
            "outcome": "answered",
            "answer": "Latest price is [[fact:price.latest]].",
            "claims": [
                {
                    "claim_id": "price",
                    "text": "Latest price is [[fact:price.latest]].",
                    "importance": "major",
                    "evidence_refs": ["citation-1"],
                    "numeric_refs": ["price.latest"],
                }
            ],
            "citations": [
                {"citation_id": "citation-1", "source_id": "source:yfinance"}
            ],
            "limitations": [],
        }
    )

    output = publish_lookup_answer(answer, _evidence())

    assert "123.4 INR" in output
    assert "citation-1" in output
    assert "https://example.test/price" in output


def test_lookup_answer_must_publish_a_claim_backed_summary() -> None:
    answer = LookupAnswerV1.model_validate(
        {
            "outcome": "answered",
            "answer": "Unsupported summary.",
            "claims": [
                {
                    "claim_id": "price",
                    "text": "Latest price is [[fact:price.latest]].",
                    "importance": "major",
                    "evidence_refs": ["citation-1"],
                    "numeric_refs": ["price.latest"],
                }
            ],
            "citations": [
                {"citation_id": "citation-1", "source_id": "source:yfinance"}
            ],
        }
    )

    with pytest.raises(PublicationError, match="lookup_answer_not_claim_backed"):
        publish_lookup_answer(answer, _evidence())


def test_lookup_answer_rejects_unknown_fields_and_invalid_importance() -> None:
    with pytest.raises(PublicationError, match="structured_report_invalid"):
        parse_lookup_answer(
            '{"outcome":"answered","answer":"ok",'
            '"claims":[],"citations":[],"unknown":true}'
        )
    with pytest.raises(PublicationError, match="structured_report_invalid"):
        parse_lookup_answer(
            '{"outcome":"answered","answer":"ok",'
            '"claims":[{"claim_id":"c","text":"ok",'
            '"importance":"medium","evidence_refs":["src"]}],'
            '"citations":[{"citation_id":"src","source_id":"price"}]}'
        )

    answer = LookupAnswerV1.model_validate(
        {
            "outcome": "answered",
            "answer": "Latest price is 999.",
            "claims": [
                {
                    "claim_id": "price",
                    "text": "Latest price is 999.",
                    "importance": "major",
                    "evidence_refs": ["citation-1"],
                    "numeric_refs": [],
                }
            ],
            "citations": [
                {"citation_id": "citation-1", "source_id": "source:yfinance"}
            ],
        }
    )
    with pytest.raises(PublicationError, match="numeric_claim_unbound"):
        publish_lookup_answer(answer, _evidence())


def test_report_validation_fallback_renders_evidence_and_limitations() -> None:
    result = report_validation_fallback(_evidence(), ("structured_report_invalid",))

    assert "Research report" in result
    assert "Verified evidence" in result
    assert "Data limitations" in result
    assert "123.4" in result


def test_report_validation_fallback_uses_professional_evidence_rendering() -> None:
    evidence = {
        "historical_prices:data.period_return_pct": EvidenceFact(
            fact_id="historical_prices:data.period_return_pct",
            value=-25.1715,
            unit="provider_value",
            source_id="source:yfinance",
            instrument="ABC.NS",
            observed_at=datetime(2026, 9, 18, tzinfo=UTC),
            quality_status="verified",
            source_url="https://finance.yahoo.com/quote/ABC.NS/history/",
        )
    }

    result = report_validation_fallback(evidence, ("structured_report_invalid",))

    assert "provider_value" not in result
    assert "-25.17%" in result
    assert "https://finance.yahoo.com/quote/ABC.NS/history/" in result
    assert "2026-09-18T00:00:00+00:00" in result


def test_report_validation_fallback_is_report_shaped_without_evidence() -> None:
    result = report_validation_fallback({}, ("evidence_unavailable",))

    assert "Research report" in result
    assert "No verified evidence was returned" in result
    assert "evidence was unavailable" in result
    assert "No financial conclusion" in result


def test_report_validation_fallback_lists_limited_sources_once() -> None:
    result = report_validation_fallback(
        _evidence(),
        availability={
            "technical_analysis": {
                "status": "available",
                "evidence_count": 1,
            },
            "news": {
                "status": "unavailable",
                "reason": "No usable evidence returned",
                "evidence_count": 0,
            },
        },
    )

    assert result.count("News unavailable: No usable evidence returned") == 1
    assert "123.4" in result
