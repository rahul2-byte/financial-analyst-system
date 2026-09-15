from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar


class SourceClassifier:
    TIER_ONE: ClassVar[set[str]] = {
        "bseindia.com",
        "nseindia.com",
        "sebi.gov.in",
        "rbi.org.in",
        "pib.gov.in",
    }
    TIER_TWO: ClassVar[set[str]] = {
        "thehindubusinessline.com",
        "finshots.in",
        "economictimes.indiatimes.com",
        "livemint.com",
        "business-standard.com",
        "moneycontrol.com",
    }
    BLOCKED: ClassVar[set[str]] = {"zacks.com", "pocketsense.com", "wisesheets.io"}

    @classmethod
    def classify(cls, domain: str) -> int:
        domain = domain.lower().strip()
        domain = domain.removeprefix("www.")
        if domain in cls.BLOCKED:
            return 4
        if domain in cls.TIER_ONE or any(
            domain.endswith(f".{item}") for item in cls.TIER_ONE
        ):
            return 1
        if domain in cls.TIER_TWO or any(
            domain.endswith(f".{item}") for item in cls.TIER_TWO
        ):
            return 2
        return 3


class QualityScorer:
    EXTRACTION_POINTS: ClassVar[dict[str, int]] = {
        "full": 25,
        "partial": 12,
        "snippet_only": 3,
        "failed": 0,
    }
    SOURCE_POINTS: ClassVar[dict[int, int]] = {1: 30, 2: 20, 3: 10, 4: 0}

    @classmethod
    def score(
        cls,
        *,
        source_tier: int,
        extraction_status: str,
        publish_time: datetime | None,
        relevance_check: bool,
        word_count: int | None,
        is_duplicate: bool,
    ) -> float:
        score = 0.0
        score += cls.SOURCE_POINTS.get(source_tier, 10)
        score += cls.EXTRACTION_POINTS.get(extraction_status, 0)

        days_old = 7.0
        if publish_time is not None:
            days_old = max(
                0.0, (datetime.now(UTC) - publish_time).total_seconds() / 86400.0
            )
        score += max(0.0, 20.0 - (days_old / 7.0) * 20.0)

        score += 15.0 if relevance_check else 0.0
        score += min(10.0, (word_count or 0) / 80.0)

        if is_duplicate:
            score *= 0.2
        return round(score, 2)
