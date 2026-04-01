"""Orchestration schemas for LangGraph pipeline - PlanData and ExecutionStep."""

from typing import List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum


class TargetAgent(str, Enum):
    MARKET_OFFLINE = "market_offline"
    MARKET_ONLINE = "market_online"
    WEB_SEARCH = "web_search"
    SENTIMENT_ANALYSIS = "sentiment_analysis"
    FUNDAMENTAL_ANALYSIS = "fundamental_analysis"
    TECHNICAL_ANALYSIS = "technical_analysis"
    CONTRARIAN_ANALYSIS = "contrarian_analysis"
    MACRO_ANALYSIS = "macro_analysis"


class ExecutionStep(BaseModel):
    """Represents a single step in the execution plan."""

    step_number: int
    target_agent: str
    parameters: dict = Field(default_factory=dict)
    dependencies: List[int] = Field(default_factory=list)


class PlannerIntentType(str, Enum):
    GREETING = "greeting"
    NON_FINANCIAL = "non_financial"
    SIMPLE_FINANCIAL = "simple_financial"
    COMPLEX_RESEARCH = "complex_research"


class PlannerResponseMode(str, Enum):
    DIRECT_RESPONSE = "direct_response"
    ASK_CLARIFICATION = "ask_clarification"
    ASK_PLAN_APPROVAL = "ask_plan_approval"
    EXECUTE_PLAN = "execute_plan"


class PlanData(BaseModel):
    """Response schema for planner agent."""

    plan_id: Optional[str] = None
    intent_type: PlannerIntentType
    response_mode: PlannerResponseMode
    is_financial_request: bool = True
    scope: Optional[str] = None
    assistant_response: Optional[str] = None
    clarifying_questions: Optional[List[str]] = None
    proposed_plan: Optional[str] = None
    requires_user_approval: bool = False
    execution_steps: List[ExecutionStep] = Field(default_factory=list)


class OfflineStatus(BaseModel):
    """Result from the intelligent market offline agent."""

    data_available: bool = Field(description="Whether the requested data is in the database")
    ticker_used: str = Field(description="The ticker symbol that was finally verified")
    reasoning: str = Field(description="Brief explanation of the availability check")
    extra_info: dict = Field(default_factory=dict, description="Additional context from tools")


class DataStatus(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    MISSING = "missing"
    UNKNOWN = "unknown"


class DatasetManifest(BaseModel):
    """Status of a specific dataset for a ticker."""

    dataset_type: str  # e.g., "ohlcv", "fundamentals", "news"
    status: DataStatus
    last_updated: Optional[str] = None
    available_range: Optional[str] = None
    extra_info: Optional[dict] = None


class DataManifest(BaseModel):
    """Overall data availability manifest for a query."""

    ticker: str
    is_grounded: bool = False
    datasets: List[DatasetManifest] = Field(default_factory=list)
    recommended_range: str = Field(description="Planner's recommended time range (e.g., '5y')")
    user_approved: bool = False
    missing_required: List[str] = Field(default_factory=list)


class ConflictRecord(BaseModel):
    """Tracks contradictions between research agents."""

    contending_agents: List[str]
    is_resolved: bool = False
    iteration_count: int = 0
    agent_outputs: dict = Field(default_factory=dict)
    final_perspective: Optional[str] = None  # Combined perspective if conflict persists
