from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class AgentExecutionMode(str, Enum):
    CONTINUE = "continue"
    WAIT_FOR_APPROVAL = "wait_for_approval"
    BRANCH = "branch"
    STOP = "stop"


class AnalyzeFundamentalsParams(BaseModel):
    ticker: str = Field(..., description="The stock ticker symbol.")
    raw_data: Dict[str, Any] = Field(
        ...,
        description="The raw fundamental data dictionary fetched from the online agent or database.",
    )


# --- Sentiment & Qualitative Schemas ---


class EntityImpact(BaseModel):
    entity_name: str = Field(
        ..., description="Name of the company, competitor, or supplier mentioned."
    )
    relationship: str = Field(
        ..., description="E.g., 'Competitor', 'Supplier', 'Subsidiary', 'Client'."
    )
    impact: str = Field(
        ..., description="'Bullish', 'Bearish', or 'Neutral' impact on this entity."
    )


class QualitativeInsights(BaseModel):
    # Stage 1 Data (Deterministic NLP output)
    finbert_overall_score: str = Field(
        ..., description="The overall mathematical sentiment score."
    )
    finbert_guidance_score: str = Field(
        ...,
        description="The mathematical sentiment score specifically for future guidance.",
    )

    # Stage 2 Data (Extracted by LLM reasoning)
    order_book_updates: List[str] = Field(
        default_factory=list,
        description="Specific project wins, contract values, or losses.",
    )
    major_challenges: List[str] = Field(
        default_factory=list,
        description="Specific headwinds, regulatory issues, or supply chain problems.",
    )
    entity_impact_map: List[EntityImpact] = Field(
        default_factory=list,
        description="Other companies affected by this news/transcript.",
    )

    # Advanced: Contradiction Engine
    is_contradictory: bool = Field(
        ...,
        description="True if the extracted text contradicts the mathematical FinBERT score (e.g. text says debt default, but score is Bullish).",
    )
    contradiction_reason: Optional[str] = Field(
        None, description="Explanation of why there is a contradiction, if any."
    )

    # Final Synthesis
    executive_summary: str = Field(
        ...,
        description="A cohesive 2-3 paragraph professional summary of the qualitative data.",
    )


class AnalyzeSentimentParams(BaseModel):
    text_data: str = Field(
        ...,
        description="The raw text (news articles or earnings call transcripts) to analyze.",
    )


# --- Macro Economics Schemas ---


class MacroInsights(BaseModel):
    summary: str = Field(..., description="Summary of global/national economic events.")
    impact_on_markets: str = Field(
        ...,
        description="How these events likely affect the stock market (e.g., 'Bearish due to rate hikes').",
    )
    key_indicators: Dict[str, str] = Field(
        default_factory=dict,
        description="Key metrics like interest rates, inflation, or commodity prices mentioned.",
    )
    risk_level: str = Field(
        ...,
        description="Overall economic risk level: 'Low', 'Moderate', 'High', 'Extreme'.",
    )


class AgentResponse(BaseModel):
    status: str = Field(..., description="'success' or 'failure'")
    execution_mode: AgentExecutionMode = Field(
        default=AgentExecutionMode.CONTINUE,
        description="Controls the flow of the entire agent system. CONTINUE=proceed, WAIT_FOR_APPROVAL=ask user, BRANCH=switch agent, STOP=end execution."
    )
    data: dict = Field(default_factory=dict, description="The returned data payload")
    errors: Optional[List[str]] = Field(None, description="List of errors if any")
