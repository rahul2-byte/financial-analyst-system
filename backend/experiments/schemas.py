from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DatasetRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    currency: str = Field(min_length=3, max_length=3)
    timezone: str = Field(min_length=1)
    adjustment: Literal["adjusted", "unadjusted"]
    as_of: datetime
    tickers: tuple[str, ...] = Field(min_length=1)


class CostSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    commission_bps: float = Field(ge=0)
    spread_bps: float = Field(ge=0)
    slippage_bps: float = Field(ge=0)

    @field_validator("commission_bps", "spread_bps", "slippage_bps")
    @classmethod
    def finite(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("cost must be finite")
        return value


class PortfolioLimits(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_asset_weight: float = Field(gt=0, le=1)
    max_gross_exposure: float = Field(gt=0, le=1)
    min_cash_weight: float = Field(ge=0, le=1)
    max_sector_weight: float | None = Field(default=None, gt=0, le=1)
    max_holdings: int = Field(gt=0)
    max_turnover: float = Field(gt=0, le=2)
    allow_fractional: bool = False

    @model_validator(mode="after")
    def coherent(self) -> PortfolioLimits:
        if self.min_cash_weight + self.max_gross_exposure > 1:
            raise ValueError("minimum cash plus gross exposure cannot exceed 100%")
        return self


class ValidationSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: Literal["expanding", "rolling"] = "expanding"
    minimum_train_bars: int = Field(gt=0)
    test_bars: int = Field(gt=0)
    step_bars: int = Field(gt=0)
    embargo_bars: int = Field(ge=0)
    label_horizon_bars: int = Field(default=0, ge=0)


class ExperimentSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    dataset: DatasetRef
    start: datetime
    end: datetime
    bar_frequency: Literal["1d"] = "1d"
    initial_cash: float = Field(gt=0)
    base_currency: str = Field(min_length=3, max_length=3)
    execution_price: Literal["next_open"] = "next_open"
    costs: CostSpec
    limits: PortfolioLimits
    validation: ValidationSpec
    seed: int | None = None

    @model_validator(mode="after")
    def coherent(self) -> ExperimentSpec:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("experiment dates must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("experiment start must precede end")
        if self.dataset.currency != self.base_currency:
            raise ValueError("dataset and experiment currency must match")
        if not set(self.dataset.tickers):
            raise ValueError("at least one ticker is required")
        return self
