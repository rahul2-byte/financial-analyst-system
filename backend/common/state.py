from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.core.contracts.tool_result import ToolResult


class TaskMetadata(BaseModel):
    agent: str
    status: str
    attempts: int = 0
    validation_history: List[Dict[str, Any]] = Field(default_factory=list)
    failure_reason: Optional[str] = None


class ResearchState(BaseModel):
    query: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tool_registry: List[ToolResult] = Field(default_factory=list)
    agent_outputs: Dict[str, Any] = Field(default_factory=dict)
    verification_errors: List[str] = Field(default_factory=list)
    retry_count: int = 0
    global_status: str = "IN_PROGRESS"
    tasks_metadata: Dict[str, TaskMetadata] = Field(default_factory=dict)
