from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class OHLCVData(BaseModel):
    ticker: str = Field(..., description="Stock Ticker Symbol")
    date: datetime = Field(..., description="Date of the candle")
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: Optional[float] = None

    class Config:
        from_attributes = True
