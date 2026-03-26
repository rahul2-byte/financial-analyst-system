from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class AgentExecutionMode(str, Enum):
    CONTINUE = "continue"
    WAIT_FOR_APPROVAL = "wait_for_approval"
    BRANCH = "branch"
    STOP = "stop"


class ValidateReportParams(BaseModel):
    user_query: str = Field(..., description="The original query from the user.")
    draft_report: str = Field(
        ..., description="The synthesized text that needs validation."
    )


class ValidationResult(BaseModel):
    is_valid: bool = Field(
        ...,
        description="True if the report is safe to show to the user, False if it catastrophically failed.",
    )
    violations_found: List[str] = Field(
        default_factory=list, description="A list of any rules the report broke."
    )
    final_approved_text: str = Field(
        ...,
        description="The final, sanitized text ready for the user. Rewrite any mildly non-compliant parts here.",
    )


class AgentResponse(BaseModel):
    status: str = Field(..., description="'success' or 'failure'")
    execution_mode: AgentExecutionMode = Field(
        default=AgentExecutionMode.CONTINUE,
        description="Controls the flow of the entire agent system. CONTINUE=proceed, WAIT_FOR_APPROVAL=ask user, BRANCH=switch agent, STOP=end execution.",
    )
    data: dict = Field(default_factory=dict, description="The returned data payload")
    errors: Optional[List[str]] = Field(None, description="List of errors if any")
