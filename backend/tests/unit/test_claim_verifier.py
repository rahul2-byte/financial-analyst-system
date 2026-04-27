from agents.quality.claim_verifier import verify_claims


def test_verify_claims_accepts_data_gap_claim_without_evidence_refs() -> None:
    result = verify_claims(
        [
            {
                "claim_id": "c-gap",
                "importance": "major",
                "text": "Unable to assess debt because debt-to-equity data is missing.",
                "evidence_refs": [],
            }
        ],
        citation_index={},
        evidence_strength=0.0,
    )

    assert result.verified_claim_ids == ["c-gap"]
    assert result.invalid_major_claim_ids == []
    assert result.verification_details["c-gap"] == "Verified data-gap claim"


def test_verify_claims_rejects_major_claim_without_evidence_refs_when_not_data_gap() -> None:
    result = verify_claims(
        [
            {
                "claim_id": "c1",
                "importance": "major",
                "text": "Margins will expand meaningfully next year.",
                "evidence_refs": [],
            }
        ],
        citation_index={},
        evidence_strength=0.0,
    )

    assert result.verified_claim_ids == []
    assert result.invalid_major_claim_ids == ["c1"]


def test_verify_claims_rejects_major_claim_with_unknown_evidence_ref() -> None:
    result = verify_claims(
        [
            {
                "claim_id": "c2",
                "importance": "major",
                "text": "Management commentary shows margin risk.",
                "evidence_refs": ["missing-ev"],
            }
        ],
        citation_index={"known-ev": {"source": "Reuters"}},
        evidence_strength=0.8,
    )

    assert result.verified_claim_ids == []
    assert result.invalid_major_claim_ids == ["c2"]
    assert result.verification_details["c2"] == "Invalid evidence refs: missing-ev"


def test_verify_claims_accepts_known_evidence_ref() -> None:
    result = verify_claims(
        [
            {
                "claim_id": "c3",
                "importance": "major",
                "text": "Management commentary shows margin risk.",
                "evidence_refs": ["ev-1"],
            }
        ],
        citation_index={"ev-1": {"source": "Reuters"}},
        evidence_strength=0.8,
    )

    assert result.verified_claim_ids == ["c3"]
    assert result.invalid_major_claim_ids == []


def test_verify_claims_emits_opik_trace(monkeypatch):
    import app.core.observability as obs
    metadata_calls = []

    class MockOpikContext:
        def update_current_span(self, metadata=None):
            if metadata:
                metadata_calls.append(metadata)

    monkeypatch.setattr(obs, "opik_context", MockOpikContext())
    import agents.quality.claim_verifier as claim_verifier
    monkeypatch.setattr(claim_verifier, "opik_context", MockOpikContext(), raising=False)

    verify_claims = claim_verifier.verify_claims
    verify_claims([], {}, 0.5)

    assert len(metadata_calls) > 0
    assert any("claims_checked" in m for m in metadata_calls)
