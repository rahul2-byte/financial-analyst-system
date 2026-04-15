from datetime import datetime
from typing import Dict, List, Optional, TypeAlias

from pydantic import BaseModel

MetadataValue: TypeAlias = str | int | float | bool | None


class NewsArticle(BaseModel):
    ticker: str
    title: str
    url: str
    source: str
    published_date: datetime
    summary: Optional[str] = None
    content: str
    company_name: Optional[str] = None
    query_objective: Optional[str] = None
    query_variant: Optional[str] = None
    intent_type: Optional[str] = None
    search_rank: Optional[int] = None
    search_provider: Optional[str] = None
    source_domain: Optional[str] = None
    source_type: Optional[str] = None
    source_priority: Optional[int] = None
    original_url: Optional[str] = None
    canonical_url: Optional[str] = None
    resolved_url: Optional[str] = None
    fetched_at: Optional[datetime] = None
    language: Optional[str] = None
    content_hash: Optional[str] = None
    title_hash: Optional[str] = None
    article_hash: Optional[str] = None
    is_trusted_domain: Optional[bool] = None
    dedupe_key: Optional[str] = None
    timeframe: Optional[str] = None
    run_id: Optional[str] = None


class ProcessedChunk(BaseModel):
    chunk_id: str
    ticker: str
    text: str
    metadata: Dict[str, MetadataValue]
    embedding: Optional[List[float]] = None
