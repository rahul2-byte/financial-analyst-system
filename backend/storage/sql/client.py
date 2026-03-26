from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlmodel import SQLModel, Session, create_engine, select, func, text
from config.settings import settings
from data.interfaces.storage import IStructuredStorage
from data.schemas.market import OHLCVData
from storage.sql.models import (
    OHLCV,
    CompanyFundamentals,
    FinancialStatements,
    MacroIndicators,
)


class PostgresClient(IStructuredStorage):
    def __init__(self):
        self.engine = create_engine(settings.DATABASE_URL)
        SQLModel.metadata.create_all(self.engine)

    def is_db_up(self) -> bool:
        """Check if the database is up and running."""
        try:
            with Session(self.engine) as session:
                session.execute(text("SELECT 1")).first()
            return True
        except Exception:
            return False

    def has_any_data(self) -> bool:
        """Check if the OHLCV table has any data."""
        with Session(self.engine) as session:
            result = session.execute(text("SELECT 1 FROM ohlcv_data LIMIT 1")).first()
            return result is not None

    def get_ticker_info(self, ticker: str) -> Dict[str, Any]:
        """Get date range, row count, and data presence for a specific ticker."""
        with Session(self.engine) as session:
            statement = text(
                "SELECT count(id), min(date), max(date) FROM ohlcv_data WHERE ticker = :ticker"
            )
            result = session.execute(statement, {"ticker": ticker}).first()

            if result and result[0] > 0:
                count, min_date, max_date = result
                return {
                    "ticker": ticker,
                    "ticker_found": True,
                    "has_data": True,
                    "row_count": count,
                    "earliest_date": (
                        min_date.isoformat()
                        if hasattr(min_date, "isoformat")
                        else str(min_date)
                    ),
                    "latest_date": (
                        max_date.isoformat()
                        if hasattr(max_date, "isoformat")
                        else str(max_date)
                    ),
                    "frequency": "day",
                }
            return {
                "ticker": ticker,
                "ticker_found": False,
                "has_data": False,
                "row_count": 0,
                "earliest_date": None,
                "latest_date": None,
                "frequency": None,
            }

    def get_ticker_count(self) -> int:
        """Get the total number of unique tickers in the database."""
        with Session(self.engine) as session:
            statement = text("SELECT count(DISTINCT ticker) FROM ohlcv_data")
            result = session.execute(statement).first()
            return result[0] if result else 0

    def get_table_count(self) -> int:
        """Get the number of tables in the public schema."""
        with Session(self.engine) as session:
            statement = text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"
            )
            result = session.execute(statement).first()
            return result[0] if result else 0

    def get_table_names(self) -> List[str]:
        """Get the names of all tables in the public schema."""
        with Session(self.engine) as session:
            statement = text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';"
            )
            results = session.execute(statement).fetchall()
            return [row[0] for row in results] if results else []

    def get_column_names(self, table_name: str) -> List[str]:
        """Get the column names for a specific table."""
        with Session(self.engine) as session:
            statement = text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = :table_name;"
            )
            results = session.execute(statement, {"table_name": table_name}).fetchall()
            return [row[0] for row in results] if results else []


    def get_db_size(self) -> str:
        """Get the size of the current database as a human-readable string."""
        with Session(self.engine) as session:
            statement = text(
                "SELECT pg_size_pretty(pg_database_size(current_database()));"
            )
            result = session.execute(statement).first()
            return result[0] if result else "0 bytes"

    def delete_ticker_data(self, ticker: str) -> int:
        """Delete all data for a specific ticker and return the number of rows deleted."""
        with Session(self.engine) as session:
            statement = select(OHLCV).where(OHLCV.ticker == ticker)
            results = session.exec(statement).all()
            count = len(results)
            for row in results:
                session.delete(row)
            session.commit()
            return count

    def save_ohlcv(self, data: List[OHLCVData]) -> None:
        with Session(self.engine) as session:
            for item in data:
                # Check if exists to prevent duplicates
                existing = session.exec(
                    select(OHLCV).where(
                        OHLCV.ticker == item.ticker, OHLCV.date == item.date
                    )
                ).first()

                if not existing:
                    db_item = OHLCV(
                        ticker=item.ticker,
                        date=item.date,
                        open=item.open,
                        high=item.high,
                        low=item.low,
                        close=item.close,
                        volume=item.volume,
                        adjusted_close=item.adjusted_close,
                    )
                    session.add(db_item)
            session.commit()

    def upsert_fundamentals(self, data: Dict[str, Any]) -> None:
        if "ticker" not in data or "error" in data:
            return

        with Session(self.engine) as session:
            ticker = data["ticker"]
            existing = session.exec(
                select(CompanyFundamentals).where(CompanyFundamentals.ticker == ticker)
            ).first()

            if existing:
                for key, value in data.items():
                    if hasattr(existing, key) and key != "ticker":
                        setattr(existing, key, value)
                existing.updated_at = datetime.utcnow()
                session.add(existing)
            else:
                new_fund = CompanyFundamentals(
                    ticker=ticker,
                    name=data.get("name"),
                    industry=data.get("industry"),
                    sector=data.get("sector"),
                    market_cap=data.get("marketCap"),
                    pe_ratio=data.get("peRatio"),
                    forward_pe=data.get("forwardPE"),
                    peg_ratio=data.get("pegRatio"),
                    price_to_book=data.get("priceToBook"),
                    debt_to_equity=data.get("debtToEquity"),
                    return_on_equity=data.get("returnOnEquity"),
                    profit_margins=data.get("profitMargins"),
                    revenue_growth=data.get("revenueGrowth"),
                    earnings_growth=data.get("earningsGrowth"),
                    dividend_yield=data.get("dividendYield"),
                    current_price=data.get("currentPrice"),
                    target_mean_price=data.get("targetMeanPrice"),
                    fifty_two_week_high=data.get("fiftyTwoWeekHigh"),
                    fifty_two_week_low=data.get("fiftyTwoWeekLow"),
                )
                session.add(new_fund)
            session.commit()

    def upsert_financial_statements(self, data: Dict[str, Any]) -> None:
        if "ticker" not in data or "error" in data:
            return

        with Session(self.engine) as session:
            ticker = data["ticker"]
            existing = session.exec(
                select(FinancialStatements).where(FinancialStatements.ticker == ticker)
            ).first()

            if existing:
                existing.income_statement = data.get("income_statement", {})
                existing.balance_sheet = data.get("balance_sheet", {})
                existing.cash_flow = data.get("cash_flow", {})
                existing.updated_at = datetime.utcnow()
                session.add(existing)
            else:
                new_stmt = FinancialStatements(
                    ticker=ticker,
                    income_statement=data.get("income_statement", {}),
                    balance_sheet=data.get("balance_sheet", {}),
                    cash_flow=data.get("cash_flow", {}),
                )
                session.add(new_stmt)
            session.commit()

    def upsert_macro_indicators(self, data: Dict[str, Any]) -> None:
        if "error" in data:
            return

        with Session(self.engine) as session:
            new_macro = MacroIndicators(
                nifty_50=data.get("NIFTY_50"),
                india_vix=data.get("INDIA_VIX"),
                usd_inr=data.get("USD_INR"),
                crude_oil=data.get("CRUDE_OIL"),
                gold=data.get("GOLD"),
            )
            session.add(new_macro)
            session.commit()

    def get_ohlcv(
        self,
        ticker: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[OHLCVData]:
        """Get OHLCV data for a ticker, optionally bounded by dates."""
        with Session(self.engine) as session:
            statement = select(OHLCV).where(OHLCV.ticker == ticker)
            if start_date:
                statement = statement.where(OHLCV.date >= start_date)
            if end_date:
                statement = statement.where(OHLCV.date <= end_date)

            statement = statement.order_by(text("date"))
            results = session.exec(statement).all()
            return [OHLCVData.model_validate(r) for r in results]

    def get_latest_date(self, ticker: str) -> Optional[datetime]:
        with Session(self.engine) as session:
            statement = select(func.max(OHLCV.date)).where(OHLCV.ticker == ticker)
            result = session.exec(statement).first()
            return result

    def get_earliest_date(self, ticker: str) -> Optional[datetime]:
        with Session(self.engine) as session:
            statement = select(func.min(OHLCV.date)).where(OHLCV.ticker == ticker)
            result = session.exec(statement).first()
            return result
