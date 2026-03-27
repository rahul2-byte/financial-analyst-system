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
