from typing import Optional, Dict, Any
from sqlmodel import Field, SQLModel, JSON, Column
from datetime import datetime
from sqlalchemy import UniqueConstraint


class OHLCV(SQLModel, table=True):
    __tablename__ = "ohlcv_data"
    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_ohlcv_ticker_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    date: datetime = Field(index=True)
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: Optional[float] = None


class CompanyFundamentals(SQLModel, table=True):
    __tablename__ = "company_fundamentals"

    ticker: str = Field(primary_key=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    name: Optional[str] = None
    industry: Optional[str] = None
    sector: Optional[str] = None
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    price_to_book: Optional[float] = None
    debt_to_equity: Optional[float] = None
    return_on_equity: Optional[float] = None
    profit_margins: Optional[float] = None
    revenue_growth: Optional[float] = None
    earnings_growth: Optional[float] = None
    dividend_yield: Optional[float] = None
    current_price: Optional[float] = None
    target_mean_price: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None


class FinancialStatements(SQLModel, table=True):
    __tablename__ = "financial_statements"

    ticker: str = Field(primary_key=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    income_statement: Dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    balance_sheet: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    cash_flow: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class MacroIndicators(SQLModel, table=True):
    __tablename__ = "macro_indicators"

    date: datetime = Field(default_factory=datetime.utcnow, primary_key=True)
    nifty_50: Optional[float] = None
    india_vix: Optional[float] = None
    usd_inr: Optional[float] = None
    crude_oil: Optional[float] = None
    gold: Optional[float] = None


class CacheIndex(SQLModel, table=True):
    """System-wide cache index for tracking data freshness."""

    __tablename__ = "cache_index"
    __table_args__ = (UniqueConstraint("ticker", "dataset_type", name="uq_cache_ticker_dataset"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    dataset_type: str = Field(index=True)  # "ohlcv", "fundamentals", "news"
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    available_range: Optional[str] = None
    extra_info: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class ResearchAuditLog(SQLModel, table=True):
    """Persistent storage for agent execution logs."""

    __tablename__ = "research_audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    query_id: str = Field(index=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent_name: str
    action: str
    data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
