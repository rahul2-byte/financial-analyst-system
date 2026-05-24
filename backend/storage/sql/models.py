from typing import Optional, Dict, Any, List
from datetime import datetime, UTC
from uuid import uuid4

from sqlalchemy import UniqueConstraint, Index
from sqlmodel import Field, SQLModel, JSON, Column

from storage.sql.memory_models import ErrorLog, InteractionLog, PerformanceMetric

__all__ = [
    "OHLCV",
    "CompanyFundamentals",
    "FinancialStatements",
    "MacroIndicators",
    "CacheIndex",
    "ResearchAuditLog",
    "InstrumentMaster",
    "InstrumentAlias",
    "TextChunk",
    "ErrorLog",
    "InteractionLog",
    "PerformanceMetric",
]

try:
    from pgvector.sqlalchemy import Vector
except ModuleNotFoundError:  # pragma: no cover
    # Keep the module importable in minimal/dev environments.
    # Production uses the real pgvector type.
    from sqlalchemy.types import UserDefinedType

    class Vector(UserDefinedType):
        def __init__(self, dim: int):
            self.dim = dim

        def get_col_spec(self) -> str:
            return f"vector({self.dim})"


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
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
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
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    income_statement: Dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    balance_sheet: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    cash_flow: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class MacroIndicators(SQLModel, table=True):
    __tablename__ = "macro_indicators"

    date: datetime = Field(default_factory=lambda: datetime.now(UTC), primary_key=True)
    nifty_50: Optional[float] = None
    india_vix: Optional[float] = None
    usd_inr: Optional[float] = None
    crude_oil: Optional[float] = None
    gold: Optional[float] = None


class CacheIndex(SQLModel, table=True):
    """System-wide cache index for tracking data freshness."""

    __tablename__ = "cache_index"
    __table_args__ = (
        UniqueConstraint("ticker", "dataset_type", name="uq_cache_ticker_dataset"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    dataset_type: str = Field(index=True)  # "ohlcv", "fundamentals", "news"
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    available_range: Optional[str] = None
    extra_info: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class ResearchAuditLog(SQLModel, table=True):
    """Persistent storage for agent execution logs."""

    __tablename__ = "research_audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    query_id: str = Field(index=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent_name: str
    action: str
    data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class InstrumentMaster(SQLModel, table=True):
    """Canonical instrument master for equity/derivatives universe."""

    __tablename__ = "instrument_master"
    __table_args__ = (
        UniqueConstraint(
            "exchange", "trading_symbol", name="uq_instrument_exchange_symbol"
        ),
        Index("ix_instrument_master_company_name", "company_name"),
        Index("ix_instrument_master_underlying_symbol", "underlying_symbol"),
        Index("ix_instrument_master_segment_expiry", "segment", "expiry"),
    )

    instrument_key: str = Field(primary_key=True)
    exchange: str = Field(index=True)
    segment: str = Field(index=True)
    trading_symbol: str = Field(index=True)
    underlying_symbol: Optional[str] = Field(default=None)
    company_name: Optional[str] = Field(default=None)
    sector: Optional[str] = None
    industry: Optional[str] = None
    instrument_type: str = Field(index=True)
    expiry: Optional[datetime] = Field(default=None, index=True)
    strike: Optional[float] = None
    option_type: Optional[str] = Field(default=None, index=True)
    lot_size: Optional[int] = None
    tick_size: Optional[float] = None
    is_active: bool = Field(default=True, index=True)
    as_of_date: Optional[datetime] = None
    source_snapshot_id: Optional[str] = Field(default=None, index=True)


class InstrumentAlias(SQLModel, table=True):
    """Explicit mapping from common names/aliases to canonical instrument keys."""

    __tablename__ = "instrument_alias"
    __table_args__ = (Index("ix_instrument_alias_text", "alias_text", unique=True),)

    id: Optional[int] = Field(default=None, primary_key=True)
    alias_text: str = Field(index=True)
    instrument_key: str = Field(index=True)


class TextChunk(SQLModel, table=True):
    __tablename__ = "text_chunks"

    # Use a UUID string to avoid DB UUID type edge-cases.
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    ticker: str = Field(index=True)
    text: str

    # "metadata" is a reserved attribute name in SQLAlchemy declarative models.
    # Keep the column name as "metadata" while using a safe Python attribute.
    metadata_: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON),
    )

    published_date: Optional[datetime] = Field(default=None)
    embedding: List[float] = Field(sa_column=Column(Vector(1024)))
