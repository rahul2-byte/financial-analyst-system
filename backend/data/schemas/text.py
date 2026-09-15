from datetime import datetime
from typing import TypeAlias

from pydantic import BaseModel

MetadataValue: TypeAlias = str | int | float | bool | None


class NewsArticle(BaseModel):
    ticker: str
    title: str
    url: str
    source: str
    published_date: datetime
    summary: str | None = None
    content: str
    company_name: str | None = None
    query_objective: str | None = None
    query_variant: str | None = None
    intent_type: str | None = None
    search_rank: int | None = None
    search_provider: str | None = None
    source_domain: str | None = None
    source_type: str | None = None
    source_priority: int | None = None
    original_url: str | None = None
    canonical_url: str | None = None
    resolved_url: str | None = None
    fetched_at: datetime | None = None
    language: str | None = None
    content_hash: str | None = None
    title_hash: str | None = None
    article_hash: str | None = None
    is_trusted_domain: bool | None = None
    dedupe_key: str | None = None
    timeframe: str | None = None
    run_id: str | None = None


class ProcessedChunk(BaseModel):
    chunk_id: str
    ticker: str
    text: str
    metadata: dict[str, MetadataValue]
