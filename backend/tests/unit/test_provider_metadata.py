from datetime import UTC, datetime

from app.core.research_schemas import EvidenceProvenance


def test_evidence_provenance_requires_explicit_market_data_metadata() -> None:
    provenance = EvidenceProvenance(
        source="fixture",
        dataset="prices",
        instrument="ABC.NS",
        observed_at=datetime(2026, 9, 18, tzinfo=UTC),
        ingested_at=datetime(2026, 9, 18, tzinfo=UTC),
        version="fixture-1",
        quality_status="verified",
        currency="INR",
        timezone="Asia/Kolkata",
        adjustment="unadjusted",
        as_of=datetime(2026, 9, 18, tzinfo=UTC),
        source_url="https://example.test/prices",
    )

    assert provenance.currency == "INR"
    assert provenance.adjustment == "unadjusted"
