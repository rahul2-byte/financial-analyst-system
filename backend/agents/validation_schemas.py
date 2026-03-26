from pydantic import BaseModel, Field
from typing import List


class AgentValidationResult(BaseModel):
    is_valid: bool = Field(description="Whether the output is valid.")
    errors_found: List[str] = Field(
        default_factory=list, description="List of specific errors found."
    )
    correction_guidance: str = Field(
        default="", description="Instructions on how to fix the errors."
    )
