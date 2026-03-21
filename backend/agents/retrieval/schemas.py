from pydantic import BaseModel, Field
from typing import Optional, List


class SearchVectorDBParams(BaseModel):
    query: str = Field(
        ..., description="The specific question or semantic query to search for."
    )
    ticker: Optional[str] = Field(
        None, description="Filter results to a specific stock ticker if needed."
    )
    limit: int = Field(5, description="Number of text chunks to retrieve.")


class AgentResponse(BaseModel):
    status: str = Field(..., description="'success' or 'failure'")
    data: dict = Field(default_factory=dict, description="The returned data payload")
    errors: Optional[List[str]] = Field(None, description="List of errors if any")
