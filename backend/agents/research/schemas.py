from pydantic import BaseModel, Field
from typing import Optional, List


class SourceCitation(BaseModel):
    title: str = Field(..., description="Title of the source webpage or article.")
    url: str = Field(..., description="The URL of the source.")
    key_fact_extracted: str = Field(
        ..., description="The specific fact or quote extracted from this source."
    )


class WebResearchResult(BaseModel):
    summary_of_findings: str = Field(
        ..., description="A clear, professional summary of the research findings."
    )
    is_breaking_news_detected: bool = Field(
        ...,
        description="True if the research uncovered breaking or very recent news that alters the context.",
    )
    potential_market_impact: str = Field(
        ..., description="Estimated impact: 'Bullish', 'Bearish', or 'Neutral'."
    )
    citations: List[SourceCitation] = Field(
        default_factory=list,
        description="A list of sources to prove the findings and avoid hallucination.",
    )


class AgentResponse(BaseModel):
    status: str = Field(..., description="'success' or 'failure'")
    data: dict = Field(default_factory=dict, description="The returned data payload")
    errors: Optional[List[str]] = Field(None, description="List of errors if any")
