from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OHLCVData(BaseModel):
    ticker: str = Field(..., description="Stock Ticker Symbol")
    date: datetime = Field(..., description="Date of the candle")
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: float | None = None

    model_config = ConfigDict(from_attributes=True)
