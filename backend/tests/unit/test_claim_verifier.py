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
