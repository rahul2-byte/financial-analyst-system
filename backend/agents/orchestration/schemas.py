from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from enum import Enum


class AgentAction(str, Enum):
    # Data Access Actions
    FETCH_LOCAL_MARKET_DATA = "fetch_local_market_data"
    FETCH_ONLINE_MARKET_DATA = "fetch_online_market_data"
    FETCH_ONLINE_NEWS = "fetch_online_news"
    SEARCH_WEB = "search_web"

    # Analysis Actions
    ANALYZE_SENTIMENT = "analyze_sentiment"
    ANALYZE_FUNDAMENTALS = "analyze_fundamentals"
    ANALYZE_TECHNICALS = "analyze_technicals"
    ANALYZE_CONTRARIAN = "analyze_contrarian"
    ANALYZE_MACRO_ECONOMICS = "analyze_macro_economics"
    SYNTHESIZE_REPORT = "synthesize_report"

    # Validation Actions
    VALIDATE_REPORT = "validate_report"


class TargetAgent(str, Enum):
    MARKET_OFFLINE = "market_offline"
    MARKET_ONLINE = "market_online"
    WEB_SEARCH = "web_search"
    SENTIMENT_ANALYSIS = "sentiment_analysis"
    FUNDAMENTAL_ANALYSIS = "fundamental_analysis"
    TECHNICAL_ANALYSIS = "technical_analysis"
    CONTRARIAN_ANALYSIS = "contrarian_analysis"
    MACRO_ANALYSIS = "macro_analysis"
    VALIDATION = "validation"


class ExecutionStep(BaseModel):
    step_number: int = Field(
        ...,
        description="Unique ID for this step (1-indexed). Used by other steps as a dependency reference.",
    )
    target_agent: TargetAgent = Field(
        ..., description="The designated agent to execute this step."
    )
    action: AgentAction = Field(
        ..., description="The specific action the agent must perform."
    )
    parameters: Dict[str, Any] = Field(
        ...,
        description="Key-value pairs of parameters required for the action. For complex/broad queries, use lists for tickers or sectors.",
    )
    dependencies: List[int] = Field(
        default_factory=list,
        description="List of step_numbers that must complete BEFORE this step. Steps with same (or empty) dependencies run in parallel.",
    )


class PlanData(BaseModel):
    plan_id: str = Field(
        ..., description="A unique identifier for this execution plan."
    )
    is_financial_request: bool = Field(
        ..., description="Whether the request is related to finance/markets/economics."
    )
    scope: str = Field(
        ...,
        description="The scope of the request (e.g., 'single_stock', 'sector_analysis', 'macro_economics', 'global_news').",
    )
    execution_steps: List[ExecutionStep] = Field(
        ..., description="The directed acyclic graph (DAG) of steps to execute."
    )


class PlanResponse(BaseModel):
    status: str = Field(..., description="Must be 'success' or 'failure'.")
    data: Optional[PlanData] = Field(
        None, description="The execution plan details. Null if status is failure."
    )
    errors: Optional[List[str]] = Field(
        None, description="List of errors if status is failure. Null otherwise."
    )
