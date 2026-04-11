from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class InteractionLog(SQLModel, table=True):
    __tablename__ = "interactions_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    query_id: str = Field(index=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    input: str
    output: str
    score: float
    retries: int = Field(default=0)
    error_type: Optional[str] = None
    correction_applied: Optional[str] = None


class ErrorLog(SQLModel, table=True):
    __tablename__ = "error_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    query_id: str = Field(index=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    error_type: str
    correction_applied: str
    details: Optional[str] = None


class PerformanceMetric(SQLModel, table=True):
    __tablename__ = "performance_metrics"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent_name: str = Field(index=True)
    success_rate: float
    average_score: float
