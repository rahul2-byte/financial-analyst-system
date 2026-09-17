from datetime import UTC, datetime

import pytest
from app.core.agent_loop.publication import (
    EvidenceFact,
    PublicationError,
    ReportDraft,
    parse_report_draft,
    publish_report,
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


def test_publish_report_rejects_unknown_source() -> None:
    draft = _draft(citations=[{"citation_id": "citation-1", "source_id": "unknown"}])

    with pytest.raises(PublicationError, match="citation_source_missing"):
        publish_report(draft, _evidence())


def test_parse_report_draft_rejects_non_json() -> None:
    with pytest.raises(PublicationError, match="structured_report_invalid"):
        parse_report_draft("plain text report")
