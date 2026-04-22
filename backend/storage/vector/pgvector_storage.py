from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any, List, Optional

from sqlmodel import Session, create_engine
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from data.interfaces.storage import IVectorStorage
from data.processors.text import TextProcessor
from data.schemas.text import ProcessedChunk
from storage.sql.models import TextChunk

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1024
RRF_K = 60
TEMPORAL_DECAY_LAMBDA = 0.05
VECTOR_CANDIDATES = 20
TEXT_CANDIDATES = 20


class PgVectorStorage(IVectorStorage):
    """Postgres/pgvector-backed vector store.

    Notes:
    - Engine creation is lazy (no connection opened until a query executes).
    - DB schema for `text_chunks` is defined in `storage.sql.models.TextChunk`.
    """

    def __init__(self) -> None:
        self._engine = create_engine(settings.DATABASE_URL, echo=False)

    def _now(self) -> datetime:
        from datetime import timezone

        return datetime.now(timezone.utc)

    def _session(self) -> Session:
        return Session(self._engine)

    @staticmethod
    def _parse_published_date(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                from datetime import timezone

                return value.replace(tzinfo=timezone.utc)
            return value
        if not value:
            return None
        if not isinstance(value, str):
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                from datetime import timezone

                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    def chunk_and_upsert(self, text: str, metadata: dict) -> List[ProcessedChunk]:
        processor = TextProcessor(use_embeddings=True)
        chunks = processor.process_and_embed(text, metadata)
        if chunks:
            self.upsert_chunks(chunks)
        return chunks

    def upsert_chunks(self, chunks: List[ProcessedChunk]) -> None:
        if not chunks:
            return

        rows: list[dict[str, Any]] = []
        for chunk in chunks:
            embedding = chunk.embedding
            if embedding is None:
                continue
            if len(embedding) != EMBEDDING_DIM:
                logger.warning(
                    "Invalid embedding dim for chunk_id=%s: got=%s expected=%s; skipping",
                    chunk.chunk_id,
                    len(embedding),
                    EMBEDDING_DIM,
                )
                continue

            metadata = dict(chunk.metadata or {})
            pub_date = self._parse_published_date(metadata.get("published_date"))
            rows.append(
                {
                    "id": chunk.chunk_id,
                    "ticker": chunk.ticker,
                    "text": chunk.text,
                    # Column name is "metadata"; model attribute is `metadata_`.
                    "metadata": metadata,
                    "published_date": pub_date,
                    "embedding": embedding,
                }
            )

        if not rows:
            return

        with self._session() as session:
            try:
                self._upsert_chunk_rows(session, rows)
                session.commit()
            except Exception:
                session.rollback()
                raise

    def _upsert_chunk_rows(self, session: Session, rows: list[dict[str, Any]]) -> None:
        stmt = pg_insert(TextChunk.__table__).values(rows)
        update_cols = {
            "ticker": stmt.excluded.ticker,
            "text": stmt.excluded.text,
            "metadata": stmt.excluded.metadata,
            "published_date": stmt.excluded.published_date,
            "embedding": stmt.excluded.embedding,
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=[TextChunk.__table__.c.id], set_=update_cols
        )
        session.exec(stmt)

    def search(
        self,
        query_embedding: Optional[List[float]] = None,
        limit: int = 5,
        query_text: Optional[str] = None,
        ticker: Optional[str] = None,
    ) -> List[ProcessedChunk]:
        vector_candidates: list[dict[str, Any]] = []
        text_candidates: list[dict[str, Any]] = []

        if query_embedding is not None and len(query_embedding) != EMBEDDING_DIM:
            logger.warning(
                "Invalid query embedding dim: got=%s expected=%s; disabling vector search",
                len(query_embedding),
                EMBEDDING_DIM,
            )
            query_embedding = None

        with self._session() as session:
            if query_embedding is not None:
                vector_candidates = self._fetch_vector_candidates(
                    session=session,
                    query_embedding=query_embedding,
                    ticker=ticker,
                    limit=VECTOR_CANDIDATES,
                )

            if query_text:
                text_candidates = self._fetch_text_candidates(
                    session=session,
                    query_text=query_text,
                    ticker=ticker,
                    limit=TEXT_CANDIDATES,
                )

        if query_text:
            fused = self._fuse_candidates(vector_candidates, text_candidates, limit)
        else:
            fused = vector_candidates[:limit]

        import json

        results: list[ProcessedChunk] = []
        for row in fused:
            metadata = dict(row.get("metadata") or {})
            emb = row.get("embedding")
            if emb is not None and not isinstance(emb, list):
                try:
                    emb = json.loads(emb) if isinstance(emb, str) else list(emb)
                except Exception:
                    emb = None

            results.append(
                ProcessedChunk(
                    chunk_id=str(row.get("id")),
                    ticker=str(row.get("ticker") or "UNKNOWN"),
                    text=str(row.get("text") or ""),
                    metadata={str(k): str(v) for k, v in metadata.items()},
                    embedding=emb,
                )
            )
        return results

    def _fetch_vector_candidates(
        self,
        *,
        session: Session,
        query_embedding: List[float],
        ticker: Optional[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        sql = sql_text("""
            SELECT id, ticker, text, metadata, published_date, embedding
            FROM text_chunks
            WHERE (:ticker IS NULL OR ticker = :ticker)
            ORDER BY embedding <=> cast(:query_embedding as vector)
            LIMIT :limit
            """)
        rows = session.exec(
            sql,
            params={
                "ticker": ticker,
                "query_embedding": query_embedding,
                "limit": int(limit),
            },
        ).all()
        return [
            {
                "id": r[0],
                "ticker": r[1],
                "text": r[2],
                "metadata": r[3],
                "published_date": r[4],
                "embedding": r[5],
            }
            for r in rows
        ]

    def _fetch_text_candidates(
        self,
        *,
        session: Session,
        query_text: str,
        ticker: Optional[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        sql = sql_text("""
            WITH ranked AS (
                SELECT id, ticker, text, metadata, published_date, embedding,
                       ts_rank_cd(to_tsvector('english', text), websearch_to_tsquery('english', :query_text)) as rank
                FROM text_chunks
                WHERE (:ticker IS NULL OR ticker = :ticker)
                  AND to_tsvector('english', text) @@ websearch_to_tsquery('english', :query_text)
            )
            SELECT id, ticker, text, metadata, published_date, embedding
            FROM ranked
            ORDER BY rank DESC
            LIMIT :limit
            """)
        rows = session.exec(
            sql,
            params={
                "ticker": ticker,
                "query_text": query_text,
                "limit": int(limit),
            },
        ).all()
        return [
            {
                "id": r[0],
                "ticker": r[1],
                "text": r[2],
                "metadata": r[3],
                "published_date": r[4],
                "embedding": r[5],
            }
            for r in rows
        ]

    def _candidate_published_date(
        self, candidate: dict[str, Any]
    ) -> Optional[datetime]:
        pub = candidate.get("published_date")
        parsed = self._parse_published_date(pub)
        if parsed is not None:
            return parsed
        metadata = candidate.get("metadata") or {}
        if isinstance(metadata, dict):
            return self._parse_published_date(metadata.get("published_date"))
        return None

    def _fuse_candidates(
        self,
        vector_candidates: list[dict[str, Any]],
        text_candidates: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        # Reciprocal Rank Fusion.
        scores: dict[str, float] = {}
        items: dict[str, dict[str, Any]] = {}

        for rank, row in enumerate(vector_candidates):
            cid = str(row.get("id"))
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rank + 1 + RRF_K)
            items[cid] = row

        for rank, row in enumerate(text_candidates):
            cid = str(row.get("id"))
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rank + 1 + RRF_K)
            if cid not in items:
                items[cid] = row

        now = self._now()
        rescored: list[tuple[dict[str, Any], float]] = []
        for cid, rrf_score in scores.items():
            row = items[cid]
            pub_date = self._candidate_published_date(row)
            days_old = 0
            if pub_date is not None:
                delta_days = (now - pub_date).total_seconds() / 86400.0
                days_old = max(0, int(delta_days))
            decay = math.exp(-TEMPORAL_DECAY_LAMBDA * days_old)
            rescored.append((row, rrf_score * decay))

        rescored.sort(key=lambda x: x[1], reverse=True)
        return [row for row, _ in rescored[: int(limit)]]

    def list_recent_by_tickers(
        self, tickers: List[str], limit: int = 20
    ) -> List[ProcessedChunk]:
        """Return recent text chunks for the given tickers.

        This method is used for materialization / cache reuse flows where callers
        need the raw text and metadata. Embeddings are intentionally *not* loaded
        because:

        - They are large and unnecessary for these code paths.
        - Some DB drivers may return `vector` columns as strings; naive conversion
          (e.g. `list(emb)`) can produce a list of characters and trigger
          `ProcessedChunk` validation errors.

        If you need embeddings for similarity search, use `search()`.
        """

        if not tickers:
            return []

        with self._session() as session:
            sql = sql_text("""
                SELECT id, ticker, text, metadata, published_date
                FROM text_chunks
                WHERE ticker = ANY(:tickers)
                ORDER BY published_date DESC NULLS LAST
                LIMIT :limit
                """)
            rows = session.exec(
                sql, params={"tickers": tickers, "limit": int(limit)}
            ).all()

        results: list[ProcessedChunk] = []
        for row in rows:
            metadata = dict(row[3] or {})
            results.append(
                ProcessedChunk(
                    chunk_id=str(row[0]),
                    ticker=str(row[1] or "UNKNOWN"),
                    text=str(row[2] or ""),
                    metadata={str(k): str(v) for k, v in metadata.items()},
                    embedding=None,
                )
            )
        return results

    def get_news_info(self, ticker: str) -> dict:
        with self._session() as session:
            try:
                sql = sql_text(
                    "SELECT COUNT(*) FROM text_chunks WHERE ticker = :ticker"
                )
                count = int(session.exec(sql, params={"ticker": ticker}).one()[0])
                return {
                    "ticker": ticker,
                    "news_count": count,
                    "has_news": count > 0,
                }
            except Exception as e:
                logger.error("Error counting news in pgvector storage: %s", e)
                return {
                    "ticker": ticker,
                    "news_count": 0,
                    "has_news": False,
                    "error": str(e),
                }
