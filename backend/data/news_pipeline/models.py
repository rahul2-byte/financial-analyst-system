from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class CompanyContext:
    ticker: str
    company_name: str
    market: str = "IN"
    nse_symbol: str | None = None
    bse_code: str | None = None
    sector: str | None = None


@dataclass(slots=True)
class RawSearchResult:
    ticker: str
    company_name: str
    market: str
    title: str
    url: str
    source_domain: str
    source_type: str
    query_intent: str
    search_provider: str
    snippet: str = ""
    author: str | None = None
    publish_time: datetime | None = None
    original_url: str | None = None
    canonical_url: str | None = None


@dataclass(slots=True)
class ExtractionResult:
    article_text: str | None
    word_count: int | None
    extraction_status: str
    paywall_detected: bool
    relevance_check: bool


@dataclass(slots=True)
class NewsPipelineRecord:
    ticker: str
    company_name: str
    market: str
    url: str
    canonical_url: str
    title: str
    author: str | None
    snippet: str
    article_text: str | None
    word_count: int | None
    publish_time: datetime | None
    retrieval_time: datetime
    source_domain: str
    source_type: str
    source_tier: int
    paywall_detected: bool
    extraction_status: str
    quality_score: float
    relevance_check: bool
    is_duplicate: bool
    cluster_id: str | None
    query_intent: str
    search_provider: str
    pipeline_version: str
