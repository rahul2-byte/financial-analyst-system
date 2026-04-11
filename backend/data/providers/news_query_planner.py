from typing import Any
import re

from data.providers.search_time_range import normalize_ddgs_time_range


QUERY_SPECS = (
    {
        "intent_type": "company_news",
        "suffix": "latest company news strategic updates",
        "keywords": ["company news", "strategic update", "management"],
        "preferred_domains": ["reuters.com", "bloomberg.com", "cnbc.com"],
    },
    {
        "intent_type": "earnings",
        "suffix": "earnings results guidance transcript",
        "keywords": ["earnings", "results", "guidance"],
        "preferred_domains": ["seekingalpha.com", "company filings", "reuters.com"],
    },
    {
        "intent_type": "business_drivers",
        "suffix": "business drivers growth demand pricing expansion",
        "keywords": ["growth drivers", "demand", "pricing"],
        "preferred_domains": ["reuters.com", "wsj.com", "ft.com"],
    },
    {
        "intent_type": "macro_sector",
        "suffix": "sector trends regulation competition macro outlook",
        "keywords": ["sector trends", "regulation", "competition"],
        "preferred_domains": ["reuters.com", "ft.com", "economist.com"],
    },
    {
        "intent_type": "risks_sentiment",
        "suffix": "risks concerns analyst sentiment controversies",
        "keywords": ["risks", "analyst sentiment", "concerns"],
        "preferred_domains": ["reuters.com", "marketwatch.com", "cnbc.com"],
    },
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "build",
    "for",
    "focus",
    "latest",
    "of",
    "on",
    "research",
    "stock",
    "the",
    "to",
}


def _normalize_time_range(timeframe: str | None) -> str:
    if timeframe and str(timeframe).strip().lower() in {"1y", "1 year"}:
        return "y"
    if timeframe and str(timeframe).strip().lower() == "6m":
        return "m"
    return normalize_ddgs_time_range(timeframe, default="m") or "m"


def _build_subject(company_name: str | None, ticker: str | None) -> str:
    if company_name and company_name.strip():
        return company_name.strip()
    if ticker and ticker.strip():
        return ticker.strip()
    return "company"


def _build_objective_context(objective: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", objective.lower())
    context_tokens: list[str] = []
    for token in tokens:
        if token in STOPWORDS or len(token) <= 2:
            continue
        if token in context_tokens:
            continue
        context_tokens.append(token)
        if len(context_tokens) == 4:
            break

    return " ".join(context_tokens)


def build_news_query_plan(
    objective: str,
    ticker: str | None,
    company_name: str | None,
    timeframe: str | None,
    conversation_history: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    # Preserve the interface for upstream planners while keeping query generation deterministic.
    del conversation_history

    subject = _build_subject(company_name, ticker)
    time_range = _normalize_time_range(timeframe)
    objective_context = _build_objective_context(objective)
    queries = []

    for priority, spec in enumerate(QUERY_SPECS, start=1):
        query = f"{subject} {spec['suffix']}"
        if objective_context:
            query = f"{subject} {objective_context} {spec['suffix']}"
        queries.append(
            {
                "intent_type": spec["intent_type"],
                "query": query,
                "keywords": list(spec["keywords"]),
                "preferred_domains": list(spec["preferred_domains"]),
                "time_range": time_range,
                "priority": priority,
            }
        )

    return {
        "objective": objective,
        "ticker": ticker,
        "company_name": company_name,
        "timeframe": timeframe,
        "queries": queries,
    }
