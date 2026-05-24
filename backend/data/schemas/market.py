from pydantic import BaseModel, Field, ConfigDict
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

    model_config = ConfigDict(from_attributes=True)
