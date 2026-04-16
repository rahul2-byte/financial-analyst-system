from pydantic import ValidationError
import pytest

from app.core.research_schemas import EvidenceRecord, ResearchAgentResult


def test_research_agent_result_requires_explicit_status_and_findings():
    with pytest.raises(ValidationError):
        ResearchAgentResult.model_validate({"agent": "fundamental_analysis"})


def test_evidence_record_requires_provenance_fields():
    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate({"text": "missing provenance"})
