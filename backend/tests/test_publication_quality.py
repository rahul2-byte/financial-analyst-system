"""Sources dedupe and Data gaps section in published answers."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.agent_loop.publication import (
    EvidenceFact,
    ReportCitation,
    ReportClaim,
    ReportDraft,
    publish_report,
    report_validation_fallback,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_GAP = "No price data for TATAMOTORS.NS; the symbol may have changed."
_FAILED = {
    "market_data": {
        "source": "market_data",
        "status": "unavailable",
        "reason": _GAP,
        "evidence_count": 0,
    }
}
_OK = {
    "fundamentals": {
        "source": "fundamentals",
        "status": "available",
        "reason": None,
        "evidence_count": 3,
    }
}


def _facts(count: int = 10) -> dict[str, EvidenceFact]:
    return {
        f"f:{i}": EvidenceFact(
            fact_id=f"f:{i}",
            value=float(i),
            unit="INR",
            source_id="fundamentals_snapshot",
            instrument="X",
            observed_at=_NOW,
            quality_status="verified",
            source_url="https://api.upstox.com",
        )
        for i in range(count)
    }


def _draft() -> ReportDraft:
    return ReportDraft(
        executive_summary="Summary without figures.",
        key_drivers=["Driver"],
        detailed_analysis="Analysis.",
        risks=["Risk"],
        final_view="View.",
        claims=[
            ReportClaim(
                claim_id="c1",
                text="Claim",
                importance="minor",
                evidence_refs=["r1"],
            )
        ],
        citations=[ReportCitation(citation_id="r1", source_id="fundamentals_snapshot")],
    )


def test_duplicate_sources_render_once() -> None:
    text = report_validation_fallback(_facts(), availability=_OK)
    assert text.count("- fundamentals_snapshot: https://api.upstox.com") == 1


def test_failed_tool_error_under_data_gaps() -> None:
    text = report_validation_fallback(_facts(), availability=_FAILED)
    gaps = text.split("## Data gaps\n", 1)[1].split("\n\n", 1)[0]
    assert gaps == f"- Price history: {_GAP}"


def test_no_data_gaps_when_all_succeeded() -> None:
    assert "Data gaps" not in report_validation_fallback(_facts(), availability=_OK)
    assert "Data gaps" not in publish_report(_draft(), _facts(), None, _OK)


def test_data_gaps_capped_at_five() -> None:
    many = {
        f"s{i}": {"source": f"s{i}", "status": "unavailable", "reason": f"e{i}"}
        for i in range(8)
    }
    text = report_validation_fallback(_facts(), availability=many)
    assert text.split("## Data gaps\n", 1)[1].split("\n\n", 1)[0].count("\n- ") == 4


def test_publish_report_with_data_gaps_passes_validator() -> None:
    text = publish_report(_draft(), _facts(), None, _FAILED)
    assert f"## Data gaps\n- Price history: {_GAP}" in text
