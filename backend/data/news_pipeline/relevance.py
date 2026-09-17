from __future__ import annotations

import re
from typing import Any

RELEVANCE_FREQUENCY_THRESHOLD = 3
RELEVANCE_LEAD_CHARS = 500


def is_article_relevant(
    article: dict[str, Any],
    ticker: str,
    company_name: str | None = None,
    adr_aliases: list[str] | None = None,
    lenient: bool = False,
) -> bool:
    """Apply the news relevance guard used by current pipeline tests."""
    title = str(article.get("title", "")).strip()
    content = str(article.get("content", "")).strip()
    if not title and not content:
        return False

    targets = [ticker, company_name, *(adr_aliases or [])]
    valid_targets = [str(target).strip() for target in targets if str(target).strip()]
    if not valid_targets:
        return False

    patterns = [
        re.compile(rf"\b{re.escape(target)}\b", re.IGNORECASE)
        for target in valid_targets
    ]
    if any(pattern.search(title) for pattern in patterns):
        return True

    if not content:
        return False
    if any(pattern.search(content[:RELEVANCE_LEAD_CHARS]) for pattern in patterns):
        return True
    if lenient:
        return False
    return (
        sum(len(pattern.findall(content)) for pattern in patterns)
        >= RELEVANCE_FREQUENCY_THRESHOLD
    )
