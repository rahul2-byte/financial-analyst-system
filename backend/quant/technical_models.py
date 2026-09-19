"""Typed contracts for deterministic technical analysis evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceProvenance(BaseModel):
    source: str
    snapshot_hash: str | None = None
    adjustment: str
    timezone: str
    as_of: datetime


class IndicatorMeasurement(BaseModel):
    indicator: str
    category: str
    value: float | None = None
    unit: str | None = None
    normalized: float | None = Field(default=None, ge=-1, le=1)
    percentile: float | None = Field(default=None, ge=0, le=1)
    direction: Literal["bullish", "bearish", "neutral", "unavailable"] = "unavailable"
    strength: float | None = Field(default=None, ge=0, le=1)
    state: str = "unavailable"
    event: str | None = None
    lookback: int | None = None
    available: bool = True
    evidence_id: str


class TechnicalSnapshot(BaseModel):
    schema_version: str = "technical-snapshot-v1"
    analysis_id: str
    ticker: str
    as_of: datetime
    interval: str
    row_count: int = Field(ge=0)
    status: Literal["ok", "partial", "insufficient_data", "failed"]
    measurements: list[IndicatorMeasurement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: EvidenceProvenance
    metadata: dict[str, Any] = Field(default_factory=dict)
