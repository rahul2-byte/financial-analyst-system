from datetime import UTC, datetime

import pytest
from app.core.agent_loop.evidence import extract_evidence_facts
from app.core.agent_loop.publication import EvidenceFact
from pydantic import ValidationError


def test_verified_iso_candle_timestamp_is_available_as_a_fact() -> None:
    payload = {
        "provenance": {
            "dataset": "upstox_historical_candle",
            "instrument": "NSE_EQ|TEST",
            "quality_status": "verified",
            "observed_at": "2026-09-23T00:00:00+00:00",
            "ingested_at": "2026-09-23T00:00:01+00:00",
            "source_url": "https://example.test/candles",
        },
        "data": [{"timestamp": "2026-09-22T00:00:00+05:30", "close": 93.0}],
    }

    facts = extract_evidence_facts(payload)

    timestamp = facts["upstox_historical_candle:data.0.timestamp"]
    assert timestamp.value == "2026-09-22T00:00:00+05:30"
    assert timestamp.unit == "provider_timestamp"
    assert facts["upstox_historical_candle:data.0.close"].value == 93.0


def test_evidence_facts_reject_untyped_arbitrary_text() -> None:
    with pytest.raises(ValidationError, match="text evidence must be an ISO date"):
        EvidenceFact(
            fact_id="dataset:data.label",
            value="not a date",
            unit="provider_value",
            source_id="dataset",
            instrument="NSE_EQ|TEST",
            observed_at=datetime(2026, 9, 23, tzinfo=UTC),
            quality_status="verified",
        )
