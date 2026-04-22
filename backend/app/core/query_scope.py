from __future__ import annotations

DEEP_ANALYSIS_MARKERS = (
    "deep analysis",
    "detailed analysis",
    "full analysis",
    "full breakdown",
    "deep dive",
)

EXPLICIT_DIMENSION_MARKERS = (
    "fundamental",
    "valuation",
    "technical",
    "risk",
    "catalyst",
    "news",
    "governance",
    "cash flow",
    "asset quality",
)


def normalize_research_scope(query: str) -> str:
    normalized = str(query or "").strip()
    lowered = normalized.lower()
    if not normalized:
        return normalized

    has_broad_marker = any(marker in lowered for marker in DEEP_ANALYSIS_MARKERS)
    has_one_year_window = (
        "one year" in lowered or "1 year" in lowered or "last year" in lowered
    )
    has_explicit_dimensions = any(
        marker in lowered for marker in EXPLICIT_DIMENSION_MARKERS
    )

    if not (has_broad_marker and has_one_year_window and not has_explicit_dimensions):
        return normalized

    return (
        f"{normalized}\n\n"
        "Normalized research scope:\n"
        "- Time horizon: 1 year\n"
        "- Cover: price action, fundamentals, valuation, news flow, risks, and catalysts\n"
        "- Prefer verified and recent sources; note gaps explicitly if source coverage is incomplete"
    )
