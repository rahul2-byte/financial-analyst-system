from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from data.news_pipeline.models import CompanyContext

QUERY_INTENT_PRIORITY: dict[str, int] = {
    "breaking_news": 1,
    "earnings": 2,
    "strategic": 3,
    "regulatory_legal": 4,
    "management_changes": 5,
    "analyst_opinion": 6,
    "competitor_context": 7,
    "crisis_tracking": 8,
    "background_research": 9,
}

QueryTemplateLibrary: dict[str, list[str]] = {
    "breaking_news": [
        "{company_name} {ticker} latest news India {year}",
        "{company_name} {ticker} recent developments NSE BSE {year}",
    ],
    "earnings": [
        "{company_name} {ticker} quarterly results earnings investor presentation {year}",
        "{company_name} {ticker} board meeting results margin revenue guidance {year}",
    ],
    "strategic": [
        "{company_name} {ticker} partnership acquisition expansion launch India {year}",
        "{company_name} {ticker} capex project launch joint venture {year}",
    ],
    "regulatory_legal": [
        "{company_name} {ticker} SEBI RBI NCLT legal regulatory filing {year}",
        "{company_name} {ticker} compliance penalty notice litigation India {year}",
    ],
    "management_changes": [
        "{company_name} {ticker} CEO CFO board resignation appointment {year}",
        "{company_name} {ticker} leadership management change board update {year}",
    ],
    "analyst_opinion": [
        "{company_name} {ticker} brokerage upgrade downgrade target price India {year}",
        "{company_name} {ticker} analyst rating recommendation results reaction {year}",
    ],
    "competitor_context": [
        "{company_name} {ticker} competitors sector market share India {year}",
        "{company_name} {ticker} peer comparison industry trends India {year}",
    ],
    "crisis_tracking": [
        "{company_name} {ticker} crisis outage fraud governance debt issue {year}",
        "{company_name} {ticker} controversy disruption recall investigation India {year}",
    ],
    "background_research": [
        "{company_name} {ticker} business model segment overview India {year}",
        "{company_name} {ticker} annual report operations strategy overview {year}",
    ],
}

INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "breaking_news": ("latest", "update", "announces", "development"),
    "earnings": (
        "results",
        "earnings",
        "quarter",
        "quarterly",
        "investor presentation",
    ),
    "strategic": (
        "partnership",
        "acquisition",
        "launch",
        "expansion",
        "capex",
        "joint venture",
    ),
    "regulatory_legal": (
        "sebi",
        "rbi",
        "nclt",
        "penalty",
        "notice",
        "filing",
        "board meeting",
    ),
    "management_changes": (
        "ceo",
        "cfo",
        "board",
        "resignation",
        "appointment",
    ),
    "analyst_opinion": (
        "brokerage",
        "upgrade",
        "downgrade",
        "target price",
        "rating",
    ),
    "competitor_context": ("peer", "competitor", "market share", "industry"),
    "crisis_tracking": (
        "fraud",
        "outage",
        "crisis",
        "controversy",
        "investigation",
    ),
    "background_research": (
        "business model",
        "annual report",
        "overview",
        "operations",
        "strategy",
    ),
}


def _query_time_label(time_window_days: int) -> str:
    if time_window_days <= 7:
        return "7d"
    if time_window_days <= 31:
        return "30d"
    if time_window_days <= 92:
        return "90d"
    return "365d"


def _normalize_alias(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def derive_company_aliases(company: CompanyContext) -> list[str]:
    aliases: list[str] = []

    def add(value: str | None) -> None:
        if not value:
            return
        normalized = _normalize_alias(value)
        if normalized and normalized not in aliases:
            aliases.append(normalized)

    add(company.company_name)
    add(company.ticker)
    add(company.nse_symbol)

    company_name = _normalize_alias(company.company_name)
    cleaned = re.sub(
        r"\b(LIMITED|LTD|LIMITED\.|LTD\.)\b", "", company_name, flags=re.IGNORECASE
    )
    cleaned = _normalize_alias(cleaned)
    add(cleaned)
    if cleaned:
        add(cleaned.replace(" ", ""))

    if company.ticker and company.ticker.upper() != cleaned.replace(" ", "").upper():
        add(company.ticker.upper())

    return aliases


def build_queries_for_company(
    *,
    company: CompanyContext,
    intents: list[str],
    time_window_days: int,
) -> list[dict[str, Any]]:
    year = datetime.now(UTC).year
    sector = company.sector or "Indian equities"
    aliases = derive_company_aliases(company)
    primary_name = aliases[1] if len(aliases) > 1 and " " in aliases[1] else aliases[0]
    ordered_intents = sorted(
        intents, key=lambda item: QUERY_INTENT_PRIORITY.get(item, 999)
    )

    queries: list[dict[str, Any]] = []
    for intent in ordered_intents:
        templates = QueryTemplateLibrary.get(intent, [])
        for template in templates:
            queries.append(
                {
                    "provider": "search",
                    "intent": intent,
                    "priority": QUERY_INTENT_PRIORITY.get(intent, 999),
                    "aliases": aliases,
                    "time_window": _query_time_label(time_window_days),
                    "query": template.format(
                        company_name=primary_name,
                        ticker=company.ticker,
                        sector=sector,
                        year=year,
                    ),
                }
            )
    return queries


def infer_query_intent(title: str, snippet: str, source_type: str = "") -> str:
    haystack = f"{title} {snippet}".lower()

    if source_type.lower() == "filing":
        for intent in (
            "earnings",
            "regulatory_legal",
            "management_changes",
            "strategic",
        ):
            if any(keyword in haystack for keyword in INTENT_KEYWORDS[intent]):
                return intent
        return "regulatory_legal"

    for intent in QUERY_INTENT_PRIORITY:
        keywords = INTENT_KEYWORDS.get(intent, ())
        if any(keyword in haystack for keyword in keywords):
            return intent
    return "breaking_news"
