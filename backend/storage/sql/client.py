"""
PostgreSQL storage client for the Financial Intelligence Platform.

This module provides:
- Structured data storage for OHLCV, fundamentals, financial statements
- Connection pooling for performance
- Type-safe queries using SQLModel

Usage:
    from storage.sql.client import PostgresClient

    client = PostgresClient()
    ohlcv_data = client.get_ohlcv("RELIANCE.NS")
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, UTC
from contextlib import contextmanager
from sqlmodel import SQLModel, Session, create_engine, select, func, text
from sqlalchemy import desc
from sqlalchemy.pool import QueuePool
from app.config import settings
from app.core.ticker import parse_ticker
from data.interfaces.storage import IStructuredStorage
from data.schemas.market import OHLCVData
from storage.sql.models import (
    OHLCV,
    CompanyFundamentals,
    FinancialStatements,
    MacroIndicators,
    ErrorLog,
    InteractionLog,
    InstrumentMaster,
    PerformanceMetric,
)
from storage.sql.health_repo import HealthRepository
from storage.sql.admin_repo import AdminRepository
from storage.sql.market_repo import MarketRepository

POOL_SIZE = 5
MAX_OVERFLOW = 10
POOL_TIMEOUT = 30


class PostgresClient(IStructuredStorage):
    @staticmethod
    def _canonical_equity_ticker(ticker: str) -> str:
        return parse_ticker(ticker).canonical

    @classmethod
    def _fundamentals_lookup_variants(cls, ticker: str) -> list[str]:
        return list(parse_ticker(ticker).db_lookup_variants)

    @classmethod
    def _fundamentals_lookup_variants_for_request(cls, ticker: str) -> list[str]:
        parsed_ticker = parse_ticker(ticker)
        variants = list(parsed_ticker.db_lookup_variants)
        if parsed_ticker.exchange_suffix is None:
            return variants

        return list(dict.fromkeys([parsed_ticker.provider_symbol, *variants]))

    """
    PostgreSQL client with connection pooling.

    Features:
    - Connection pooling for performance
    - Context manager for session handling
    - Type-safe operations
    """

    _engine = None

    def __init__(self):
        self._engine = self._create_engine()
        self._create_tables()
        self._health_repo = HealthRepository(self.get_session)
        self._admin_repo = AdminRepository(self.get_session)
        self._market_repo = MarketRepository(self.get_session)

    def _ensure_repositories(self) -> None:
        if not hasattr(self, "_health_repo"):
            self._health_repo = HealthRepository(self.get_session)
        if not hasattr(self, "_market_repo"):
            self._market_repo = MarketRepository(self.get_session)
        if not hasattr(self, "_admin_repo"):
            self._admin_repo = AdminRepository(self.get_session)

    @classmethod
    def _create_engine(cls):
        """Create engine with connection pooling."""
        if cls._engine is None:
            cls._engine = create_engine(
                settings.DATABASE_URL,
                poolclass=QueuePool,
                pool_size=POOL_SIZE,
                max_overflow=MAX_OVERFLOW,
                pool_timeout=POOL_TIMEOUT,
                pool_pre_ping=True,
                echo=False,
            )
        return cls._engine

    def _create_tables(self) -> None:
        """Create all tables if they don't exist."""
        vector_available = True
        with self._engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            except Exception as e:
                import logging

                vector_available = False
                logging.getLogger(__name__).warning(
                    f"Could not create vector extension: {e}"
                )

        # If pgvector isn't installed on the running Postgres instance, table creation will
        # fail when it reaches `text_chunks.embedding vector(...)`. Keep the rest of the
        # schema usable (instrument resolver, OHLCV cache, etc.) by skipping that table.
        if vector_available:
            SQLModel.metadata.create_all(self._engine)
        else:
            non_vector_tables = [
                table
                for table in SQLModel.metadata.sorted_tables
                if table.name != "text_chunks"
            ]
            SQLModel.metadata.create_all(self._engine, tables=non_vector_tables)

        with self._engine.begin() as conn:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_trgm_company_name 
                ON instrument_master USING gin (company_name gin_trgm_ops);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_trgm_trading_symbol 
                ON instrument_master USING gin (trading_symbol gin_trgm_ops);
            """))

            if vector_available:
                # Text chunk indexes (defensive IF NOT EXISTS to support existing DBs)
                conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS ix_text_chunks_ticker
                        ON text_chunks (ticker);
                        """))

                # Optional full-text search index
                conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS ix_text_chunks_fts
                        ON text_chunks USING gin (to_tsvector('english', text));
                        """))

                # Vector ANN index: prefer hnsw, fall back to ivfflat.
                try:
                    conn.execute(text("""
                            DO $$
                            BEGIN
                                BEGIN
                                    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_text_chunks_embedding_hnsw '
                                            'ON text_chunks USING hnsw (embedding vector_cosine_ops)';
                                EXCEPTION WHEN undefined_object THEN
                                    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_text_chunks_embedding_ivfflat '
                                            'ON text_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)';
                                END;
                            END $$;
                            """))
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).warning(
                        f"Could not create vector index: {e}"
                    )

            # Ensure unique constraints for ON CONFLICT operations
            conn.execute(text("""
                DO $$ 
                BEGIN 
                    -- Clean up and add constraint for ohlcv_data
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_ohlcv_ticker_date') THEN
                        -- Remove duplicates before adding constraint to prevent failure
                        DELETE FROM ohlcv_data a USING ohlcv_data b 
                        WHERE a.id < b.id AND a.ticker = b.ticker AND a.date = b.date;
                        
                        ALTER TABLE ohlcv_data ADD CONSTRAINT uq_ohlcv_ticker_date UNIQUE (ticker, date);
                    END IF;
                    
                    -- Clean up and add constraint for cache_index
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_cache_ticker_dataset') THEN
                        DELETE FROM cache_index a USING cache_index b 
                        WHERE a.id < b.id AND a.ticker = b.ticker AND a.dataset_type = b.dataset_type;
                        
                        ALTER TABLE cache_index ADD CONSTRAINT uq_cache_ticker_dataset UNIQUE (ticker, dataset_type);
                    END IF;
                    
                    -- Clean up and add constraint for instrument_master
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_instrument_exchange_symbol') THEN
                        DELETE FROM instrument_master a USING instrument_master b 
                        WHERE a.instrument_key < b.instrument_key AND a.exchange = b.exchange AND a.trading_symbol = b.trading_symbol;
                        
                        ALTER TABLE instrument_master ADD CONSTRAINT uq_instrument_exchange_symbol UNIQUE (exchange, trading_symbol);
                    END IF;
                END $$;
            """))

    @contextmanager
    def get_session(self):
        """
        Context manager for database sessions.

        Usage:
            with client.get_session() as session:
                results = session.exec(select(OHLCV)).all()
        """
        session = Session(self._engine)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def is_db_up(self) -> bool:
        """Check if the database is up and running."""
        self._ensure_repositories()
        return self._health_repo.is_db_up()

    def check_db_status(self) -> Dict[str, Any]:
        """Check if the database is up and running (agent tool version)."""
        self._ensure_repositories()
        return self._health_repo.check_db_status()

    def bulk_upsert_instruments(self, rows: List[Dict[str, Any]]) -> Dict[str, int]:
        """Upsert instrument master rows."""
        if not rows:
            return {"inserted_or_updated": 0}

        deduped: dict[tuple[str, str], Dict[str, Any]] = {}
        for row in rows:
            exchange = str(row.get("exchange", "")).strip().upper()
            symbol = str(row.get("trading_symbol", "")).strip().upper()
            if not exchange or not symbol:
                continue
            normalized = dict(row)
            normalized["exchange"] = exchange
            normalized["trading_symbol"] = symbol
            deduped[(exchange, symbol)] = normalized

        payload_rows = list(deduped.values())
        if not payload_rows:
            return {"inserted_or_updated": 0}

        with self.get_session() as session:
            statement = text("""
                INSERT INTO instrument_master (
                    instrument_key, exchange, segment, trading_symbol, underlying_symbol,
                    company_name, sector, industry, instrument_type, expiry,
                    strike, option_type, lot_size, tick_size, is_active,
                    as_of_date, source_snapshot_id
                ) VALUES (
                    :instrument_key, :exchange, :segment, :trading_symbol, :underlying_symbol,
                    :company_name, :sector, :industry, :instrument_type, :expiry,
                    :strike, :option_type, :lot_size, :tick_size, :is_active,
                    :as_of_date, :source_snapshot_id
                )
                ON CONFLICT ON CONSTRAINT uq_instrument_exchange_symbol DO UPDATE SET
                    instrument_key = EXCLUDED.instrument_key,
                    exchange = EXCLUDED.exchange,
                    segment = EXCLUDED.segment,
                    trading_symbol = EXCLUDED.trading_symbol,
                    underlying_symbol = EXCLUDED.underlying_symbol,
                    company_name = EXCLUDED.company_name,
                    sector = EXCLUDED.sector,
                    industry = EXCLUDED.industry,
                    instrument_type = EXCLUDED.instrument_type,
                    expiry = EXCLUDED.expiry,
                    strike = EXCLUDED.strike,
                    option_type = EXCLUDED.option_type,
                    lot_size = EXCLUDED.lot_size,
                    tick_size = EXCLUDED.tick_size,
                    is_active = EXCLUDED.is_active,
                    as_of_date = EXCLUDED.as_of_date,
                    source_snapshot_id = EXCLUDED.source_snapshot_id
                """)
            session.execute(statement, payload_rows)

        return {"inserted_or_updated": len(payload_rows)}

    def search_instruments(
        self,
        query: str,
        limit: int = 10,
        segment: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search active instruments by symbol/company/underlying."""
        with self.get_session() as session:
            where_parts = ["is_active = true"]
            params: Dict[str, Any] = {"query": f"%{query}%", "limit": limit}
            if segment:
                where_parts.append("segment = :segment")
                params["segment"] = segment
            if exchange:
                where_parts.append("exchange = :exchange")
                params["exchange"] = exchange

            where_clause = " AND ".join(where_parts)
            statement = text(f"""
                SELECT instrument_key, exchange, segment, trading_symbol, underlying_symbol,
                       company_name, sector, industry, instrument_type, expiry,
                       strike, option_type, lot_size, tick_size, is_active
                FROM instrument_master
                WHERE {where_clause}
                  AND (
                    trading_symbol ILIKE :query
                    OR COALESCE(underlying_symbol, '') ILIKE :query
                    OR COALESCE(company_name, '') ILIKE :query
                  )
                ORDER BY trading_symbol ASC
                LIMIT :limit
                """)
            rows = session.execute(statement, params).mappings().all()
            return [dict(row) for row in rows]

    def search_instruments_ranked(
        self,
        query: str,
        limit: int = 10,
        exchange: Optional[str] = None,
        segment: Optional[str] = None,
        instrument_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Ranked fuzzy lookup for instrument resolution."""
        candidate = (query or "").strip()
        if not candidate:
            return []

        with self.get_session() as session:
            where_parts = ["is_active = true"]
            params: Dict[str, Any] = {
                "candidate": candidate,
                "candidate_upper": candidate.upper(),
                "candidate_prefix": f"{candidate}%",
                "candidate_like": f"%{candidate}%",
                "limit": limit,
            }
            if exchange:
                where_parts.append("exchange = :exchange")
                params["exchange"] = exchange
            if segment:
                where_parts.append("segment = :segment")
                params["segment"] = segment
            if instrument_type:
                where_parts.append("instrument_type = :instrument_type")
                params["instrument_type"] = instrument_type

            where_clause = " AND ".join(where_parts)
            statement = text(f"""
                SELECT instrument_key, exchange, segment, trading_symbol, underlying_symbol,
                       company_name, sector, industry, instrument_type, expiry,
                       strike, option_type, lot_size, tick_size, is_active,
                       GREATEST(
                           similarity(UPPER(trading_symbol), :candidate_upper),
                           similarity(UPPER(COALESCE(company_name, '')), :candidate_upper),
                           similarity(UPPER(COALESCE(underlying_symbol, '')), :candidate_upper)
                       ) AS score,
                       CASE 
                           WHEN UPPER(trading_symbol) = :candidate_upper THEN 'exact_symbol'
                           WHEN similarity(UPPER(trading_symbol), :candidate_upper) > 0.6 THEN 'trigram_symbol'
                           WHEN similarity(UPPER(COALESCE(company_name, '')), :candidate_upper) > 0.6 THEN 'trigram_company'
                           ELSE 'trigram_weak'
                       END AS match_reason
                FROM instrument_master
                WHERE {where_clause}
                  AND (
                      UPPER(trading_symbol) % :candidate_upper 
                      OR UPPER(COALESCE(company_name, '')) % :candidate_upper
                      OR UPPER(COALESCE(underlying_symbol, '')) % :candidate_upper
                  )
                ORDER BY score DESC, trading_symbol ASC
                LIMIT :limit
                """)
            rows = session.execute(statement, params).mappings().all()
            return [dict(row) for row in rows]

    def resolve_alias(self, alias_text: str) -> Optional[Dict[str, Any]]:
        """Check if candidate exactly matches a known alias and return the instrument."""
        candidate = (alias_text or "").strip().upper()
        if not candidate:
            return None

        with self.get_session() as session:
            stmt = text("""
                SELECT im.* 
                FROM instrument_alias ia
                JOIN instrument_master im ON ia.instrument_key = im.instrument_key
                WHERE UPPER(ia.alias_text) = :candidate AND im.is_active = true
                LIMIT 1
            """)
            row = session.execute(stmt, {"candidate": candidate}).mappings().first()
            return dict(row) if row else None

    def resolve_exact_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Resolve exact instrument by trading_symbol or instrument_key."""
        candidate = (symbol or "").strip().upper()
        if not candidate:
            return None

        with self.get_session() as session:
            statement = (
                select(InstrumentMaster)
                .where(InstrumentMaster.is_active == True)  # noqa: E712
                .where(
                    (func.upper(InstrumentMaster.trading_symbol) == candidate)
                    | (func.upper(InstrumentMaster.instrument_key) == candidate)
                )
            )
            row = session.exec(statement).first()
            return row.model_dump() if row else None

    def resolve_underlying(
        self,
        name_or_symbol: str,
        limit: int = 5,
        exchange: Optional[str] = None,
        segment: str = "EQ",
    ) -> List[Dict[str, Any]]:
        """Resolve likely underlying instruments for a name/symbol."""
        return self.search_instruments(
            query=name_or_symbol,
            limit=limit,
            segment=segment,
            exchange=exchange,
        )

    def get_derivative_chain(
        self,
        underlying_symbol: str,
        expiry: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get active derivative contracts for an underlying symbol."""
        symbol = (underlying_symbol or "").strip().upper()
        if not symbol:
            return []

        with self.get_session() as session:
            where_parts = [
                "is_active = true",
                "UPPER(COALESCE(underlying_symbol, '')) = :symbol",
                "segment IN ('FUT', 'OPT')",
            ]
            params: Dict[str, Any] = {"symbol": symbol, "limit": limit}
            if expiry is not None:
                where_parts.append("expiry = :expiry")
                params["expiry"] = expiry

            where_clause = " AND ".join(where_parts)
            statement = text(f"""
                SELECT instrument_key, exchange, segment, trading_symbol, underlying_symbol,
                       company_name, sector, industry, instrument_type, expiry,
                       strike, option_type, lot_size, tick_size, is_active
                FROM instrument_master
                WHERE {where_clause}
                ORDER BY expiry ASC NULLS LAST, strike ASC NULLS LAST
                LIMIT :limit
                """)
            rows = session.execute(statement, params).mappings().all()
            return [dict(row) for row in rows]

    def has_any_data(self) -> bool:
        """Check if the OHLCV table has any data."""
        self._ensure_repositories()
        return self._market_repo.has_any_data()

    def get_ticker_info(self, ticker: str) -> Dict[str, Any]:
        """Get date range, row count, and data presence for a specific ticker."""
        with self.get_session() as session:
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

    def get_fundamentals_info(self, ticker: str) -> Dict[str, Any]:
        """Get presence metadata and fundamentals snapshot for a ticker."""
        with self.get_session() as session:
            statement = text("""
                SELECT ticker, updated_at, name, industry, sector, market_cap, pe_ratio,
                       forward_pe, peg_ratio, price_to_book, debt_to_equity,
                       return_on_equity, profit_margins, revenue_growth,
                       earnings_growth, dividend_yield, current_price,
                       target_mean_price, fifty_two_week_high, fifty_two_week_low
                FROM company_fundamentals
                WHERE ticker = :ticker
                """)
            lookup_variants = self._fundamentals_lookup_variants_for_request(ticker)
            parsed_ticker = parse_ticker(ticker)
            requested_is_suffixed = parsed_ticker.exchange_suffix is not None
            best_row: dict[str, Any] | None = None
            best_score: tuple[float, int] | None = None
            completeness_fields = (
                "name",
                "industry",
                "sector",
                "market_cap",
                "pe_ratio",
                "forward_pe",
                "peg_ratio",
                "price_to_book",
                "debt_to_equity",
                "return_on_equity",
                "profit_margins",
                "revenue_growth",
                "earnings_growth",
                "dividend_yield",
                "current_price",
                "target_mean_price",
                "fifty_two_week_high",
                "fifty_two_week_low",
            )

            for candidate in lookup_variants:
                result = session.execute(statement, {"ticker": candidate}).first()
                if result:
                    row = dict(getattr(result, "_mapping", result))
                    updated_at = row.get("updated_at")
                    if requested_is_suffixed:
                        best_row = row
                        break

                    updated_at_score = (
                        updated_at.timestamp()
                        if isinstance(updated_at, datetime)
                        else float("-inf")
                    )
                    completeness_score = sum(
                        row.get(field) is not None for field in completeness_fields
                    )
                    score = (updated_at_score, completeness_score)
                    if best_score is None or score > best_score:
                        best_row = row
                        best_score = score

            if best_row:
                updated_at = best_row.get("updated_at")
                updated_at_value = (
                    updated_at.isoformat()
                    if isinstance(updated_at, datetime)
                    else str(updated_at) if updated_at is not None else None
                )
                return {
                    "ticker": self._canonical_equity_ticker(ticker),
                    "ticker_found": True,
                    "has_data": True,
                    "updated_at": updated_at_value,
                    "latest_date": updated_at_value,
                    "name": best_row.get("name"),
                    "industry": best_row.get("industry"),
                    "sector": best_row.get("sector"),
                    "marketCap": best_row.get("market_cap"),
                    "peRatio": best_row.get("pe_ratio"),
                    "forwardPE": best_row.get("forward_pe"),
                    "pegRatio": best_row.get("peg_ratio"),
                    "priceToBook": best_row.get("price_to_book"),
                    "debtToEquity": best_row.get("debt_to_equity"),
                    "returnOnEquity": best_row.get("return_on_equity"),
                    "profitMargins": best_row.get("profit_margins"),
                    "revenueGrowth": best_row.get("revenue_growth"),
                    "earningsGrowth": best_row.get("earnings_growth"),
                    "dividendYield": best_row.get("dividend_yield"),
                    "currentPrice": best_row.get("current_price"),
                    "targetMeanPrice": best_row.get("target_mean_price"),
                    "fiftyTwoWeekHigh": best_row.get("fifty_two_week_high"),
                    "fiftyTwoWeekLow": best_row.get("fifty_two_week_low"),
                }
            return {
                "ticker": self._canonical_equity_ticker(ticker),
                "ticker_found": False,
                "has_data": False,
                "updated_at": None,
                "latest_date": None,
            }

    def get_macro_info(self) -> Dict[str, Any]:
        """Get date range and row count for macro indicators."""
        with self.get_session() as session:
            statement = text(
                "SELECT count(date), min(date), max(date) FROM macro_indicators"
            )
            result = session.execute(statement).first()

            if result and result[0] > 0:
                count, min_date, max_date = result
                return {
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
                }
            return {
                "has_data": False,
                "row_count": 0,
                "earliest_date": None,
                "latest_date": None,
            }

    def get_news_cache_info(self, ticker: str) -> Dict[str, Any]:
        """Get cache info for news dataset."""
        with self.get_session() as session:
            statement = text(
                "SELECT last_updated, extra_info FROM cache_index WHERE ticker = :ticker AND dataset_type = 'news'"
            )
            result = session.execute(statement, {"ticker": ticker}).first()
            if result:
                last_updated, extra_info = result
                extra_info = extra_info or {}
                vector_ready = extra_info.get("vector_ready")
                chunk_count = int(extra_info.get("chunk_count", 0) or 0)
                has_data = bool(vector_ready) if vector_ready is not None else True
                return {
                    "ticker": ticker,
                    "has_data": has_data,
                    "latest_date": (
                        last_updated.isoformat()
                        if hasattr(last_updated, "isoformat")
                        else str(last_updated)
                    ),
                    "vector_ready": (
                        bool(vector_ready) if vector_ready is not None else None
                    ),
                    "chunk_count": chunk_count,
                }
            return {
                "ticker": ticker,
                "has_data": False,
                "latest_date": None,
                "vector_ready": None,
                "chunk_count": 0,
            }

    def get_ticker_count(self) -> int:
        """Get the total number of unique tickers in the database."""
        with self.get_session() as session:
            statement = text("SELECT count(DISTINCT ticker) FROM ohlcv_data")
            result = session.execute(statement).first()
            return result[0] if result else 0

    def get_table_count(self) -> int:
        """Get the number of tables in the public schema."""
        self._ensure_repositories()
        return self._admin_repo.get_table_count()

    def get_table_names(self) -> List[str]:
        """Get the names of all tables in the public schema."""
        self._ensure_repositories()
        return self._admin_repo.get_table_names()

    def get_column_names(self, table_name: str) -> List[str]:
        """Get the column names for a specific table."""
        self._ensure_repositories()
        return self._admin_repo.get_column_names(table_name)

    def get_db_size(self) -> str:
        """Get the size of the current database as a human-readable string."""
        self._ensure_repositories()
        return self._admin_repo.get_db_size()

    def delete_ticker_data(self, ticker: str) -> int:
        """Delete all data for a specific ticker and return the number of rows deleted."""
        with self.get_session() as session:
            statement = select(OHLCV).where(OHLCV.ticker == ticker)
            results = session.exec(statement).all()
            count = len(results)
            for row in results:
                session.delete(row)
            session.commit()
            return count

    def save_ohlcv(self, data: List[OHLCVData]) -> None:
        """Save OHLCV data to database."""
        self._ensure_repositories()
        self._market_repo.save_ohlcv(data)

    def upsert_fundamentals(self, data: Dict[str, Any]) -> None:
        """Upsert company fundamentals."""
        if "ticker" not in data or "error" in data:
            return

        with self.get_session() as session:
            ticker = data["ticker"]
            existing = session.exec(
                select(CompanyFundamentals).where(CompanyFundamentals.ticker == ticker)
            ).first()

            if existing:
                for key, value in data.items():
                    if hasattr(existing, key) and key != "ticker":
                        setattr(existing, key, value)
                existing.updated_at = datetime.now(UTC)
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

    def upsert_financial_statements(self, data: Dict[str, Any]) -> None:
        """Upsert financial statements."""
        if "ticker" not in data or "error" in data:
            return

        with self.get_session() as session:
            ticker = data["ticker"]
            existing = session.exec(
                select(FinancialStatements).where(FinancialStatements.ticker == ticker)
            ).first()

            if existing:
                existing.income_statement = data.get("income_statement", {})
                existing.balance_sheet = data.get("balance_sheet", {})
                existing.cash_flow = data.get("cash_flow", {})
                existing.updated_at = datetime.now(UTC)
                session.add(existing)
            else:
                new_stmt = FinancialStatements(
                    ticker=ticker,
                    income_statement=data.get("income_statement", {}),
                    balance_sheet=data.get("balance_sheet", {}),
                    cash_flow=data.get("cash_flow", {}),
                )
                session.add(new_stmt)

    def upsert_macro_indicators(self, data: Dict[str, Any]) -> None:
        """Upsert macro indicators."""
        if "error" in data:
            return

        with self.get_session() as session:
            new_macro = MacroIndicators(
                nifty_50=data.get("NIFTY_50"),
                india_vix=data.get("INDIA_VIX"),
                usd_inr=data.get("USD_INR"),
                crude_oil=data.get("CRUDE_OIL"),
                gold=data.get("GOLD"),
            )
            session.add(new_macro)

    def get_ohlcv(
        self,
        ticker: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[OHLCVData]:
        """Get OHLCV data for a ticker, optionally bounded by dates."""
        with self.get_session() as session:
            statement = select(OHLCV).where(OHLCV.ticker == ticker)
            if start_date:
                statement = statement.where(OHLCV.date >= start_date)
            if end_date:
                statement = statement.where(OHLCV.date <= end_date)

            statement = statement.order_by(text("date"))
            results = session.exec(statement).all()
            return [OHLCVData.model_validate(r) for r in results]

    def get_latest_date(self, ticker: str) -> Optional[datetime]:
        """Get the latest date for a ticker."""
        with self.get_session() as session:
            statement = select(func.max(OHLCV.date)).where(OHLCV.ticker == ticker)
            result = session.exec(statement).first()
            return result

    def get_earliest_date(self, ticker: str) -> Optional[datetime]:
        """Get the earliest date for a ticker."""
        with self.get_session() as session:
            statement = select(func.min(OHLCV.date)).where(OHLCV.ticker == ticker)
            result = session.exec(statement).first()
            return result

    # --- Cache Index & Audit Logging ---

    def get_cache_status(self, ticker: str) -> Dict[str, Any]:
        """Check the freshness and availability of all datasets for a ticker."""
        from storage.sql.models import CacheIndex

        status = {}
        with self.get_session() as session:
            results = session.exec(
                select(CacheIndex).where(CacheIndex.ticker == ticker)
            ).all()
            for row in results:
                status[row.dataset_type] = {
                    "last_updated": row.last_updated.isoformat(),
                    "available_range": row.available_range,
                    "extra_info": row.extra_info,
                }
        return status

    def update_cache_index(
        self,
        ticker: str,
        dataset_type: str,
        available_range: Optional[str] = None,
        extra_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update or create a cache index entry."""
        from storage.sql.models import CacheIndex

        with self.get_session() as session:
            existing = session.exec(
                select(CacheIndex).where(
                    CacheIndex.ticker == ticker, CacheIndex.dataset_type == dataset_type
                )
            ).first()

            if existing:
                existing.last_updated = datetime.now(UTC)
                if available_range:
                    existing.available_range = available_range
                if extra_info:
                    existing.extra_info.update(extra_info)
                session.add(existing)
            else:
                new_entry = CacheIndex(
                    ticker=ticker,
                    dataset_type=dataset_type,
                    available_range=available_range,
                    extra_info=extra_info or {},
                )
                session.add(new_entry)

    def log_research_action(
        self,
        query_id: str,
        agent_name: str,
        action: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an agent action to the persistent audit log."""
        from storage.sql.models import ResearchAuditLog

        with self.get_session() as session:
            log_entry = ResearchAuditLog(
                query_id=query_id,
                agent_name=agent_name,
                action=action,
                data=data or {},
            )
            session.add(log_entry)

    def log_interaction(
        self,
        *,
        query_id: str,
        input: str,
        output: str,
        score: float,
        retries: int,
        error_type: str | None,
        correction_applied: str | None = None,
    ) -> None:
        with self.get_session() as session:
            session.add(
                InteractionLog(
                    query_id=query_id,
                    input=input,
                    output=output,
                    score=score,
                    retries=retries,
                    error_type=error_type,
                    correction_applied=correction_applied,
                )
            )

    def log_error(
        self,
        *,
        query_id: str,
        error_type: str,
        correction_applied: str,
        details: str | None = None,
    ) -> None:
        with self.get_session() as session:
            session.add(
                ErrorLog(
                    query_id=query_id,
                    error_type=error_type,
                    correction_applied=correction_applied,
                    details=details,
                )
            )

    def record_performance_metric(
        self,
        *,
        agent_name: str,
        success_rate: float,
        average_score: float,
    ) -> None:
        with self.get_session() as session:
            session.add(
                PerformanceMetric(
                    agent_name=agent_name,
                    success_rate=success_rate,
                    average_score=average_score,
                )
            )

    def get_recent_interactions(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self.get_session() as session:
            rows = session.exec(
                select(InteractionLog)
                .order_by(desc(InteractionLog.timestamp))
                .limit(limit)
            ).all()
            # Materialize while the session is open to avoid detached instances.
            return [
                {
                    "query_id": row.query_id,
                    "score": row.score,
                    "error_type": row.error_type,
                    "retries": row.retries,
                    "correction_applied": row.correction_applied,
                }
                for row in rows
            ]
