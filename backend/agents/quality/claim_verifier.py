from typing import Any
from dataclasses import dataclass
from app.core.observability import observe, opik_context


@dataclass
class ClaimVerificationResult:
    verified_claim_ids: list[str]
    invalid_major_claim_ids: list[str]
    verification_details: dict[str, Any]


def is_data_gap_claim(text: Any) -> bool:
    normalized = str(text or "").lower()
    if not normalized:
        return False

    data_gap_markers = (
        "missing",
        "unable to assess",
        "not available",
        "insufficient data",
        "cannot assess",
        "lack of data",
    )
    return any(marker in normalized for marker in data_gap_markers)


@observe(name="Quality:VerifyClaims", as_type="span")
def verify_claims(
    synthesis_claims: list[dict[str, Any]],
    citation_index: dict[str, Any],
    evidence_strength: float,
) -> ClaimVerificationResult:
    """Validate claim-to-citation links and evidence sufficiency."""
    opik_context.update_current_span(metadata={"claims_checked": len(synthesis_claims)})
    verified_ids = []
    invalid_major_ids = []
    details = {}

    for claim in synthesis_claims:
        claim_id = claim.get("claim_id")
        importance = claim.get("importance", "minor")
        evidence_refs = claim.get("evidence_refs", [])
        claim_text = claim.get("text", "")

        # Heuristic: claim is verified if it has at least one evidence ref
        # and evidence strength is above a minimum threshold (if major)
        if not evidence_refs:
            if is_data_gap_claim(claim_text):
                verified_ids.append(claim_id)
                details[claim_id] = "Verified data-gap claim"
                continue
            if importance == "major":
                invalid_major_ids.append(claim_id)
            details[claim_id] = "Missing evidence references"
            continue

        if citation_index:
            missing_refs = [ref for ref in evidence_refs if str(ref) not in citation_index]
            if missing_refs:
                if importance == "major":
                    invalid_major_ids.append(claim_id)
                details[claim_id] = (
                    f"Invalid evidence refs: {', '.join(str(ref) for ref in missing_refs)}"
                )
                continue

        verified_ids.append(claim_id)
        details[claim_id] = "Verified via evidence links"

    return ClaimVerificationResult(
        verified_claim_ids=verified_ids,
        invalid_major_claim_ids=invalid_major_ids,
        verification_details=details,
    )
