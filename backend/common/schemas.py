from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SectorMetrics(BaseModel):
    sector_name: str
    volatility: float = Field(..., description="Annualized volatility of the sector")
    beta: float = Field(..., description="Beta relative to the market benchmark")
    pe_ratio: float = Field(..., description="Price-to-Earnings ratio")
    debt_to_equity: float = Field(..., description="Debt-to-Equity ratio")

    @field_validator("volatility", "beta", "pe_ratio", "debt_to_equity")
    def check_non_negative(cls, v):
        if v < 0:
            raise ValueError("Metrics must be non-negative")
        return v


class RiskScore(BaseModel):
    sector_name: str
    risk_score: float = Field(..., ge=0, le=100, description="Risk score from 0 to 100")
    risk_level: RiskLevel
    contributing_factors: List[str] = Field(default_factory=list)


class VerificationResponse(BaseModel):
    status: str = Field(..., description="Success or Failure")
    is_valid: bool = Field(
        ..., description="Whether the numeric consistency check passed"
    )
    feedback: Optional[str] = Field(
        None, description="Detailed explanation of hallucinations or errors"
    )
