from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

from agents.shared.utils import (
    derive_news_coverage_score,
    derive_news_freshness_score,
    derive_required_fields_coverage,
)


def test_news_freshness_uses_short_staleness_window() -> None:
    recent = [
        {
            "title": "Recent",
            "published": format_datetime(datetime.now(UTC) - timedelta(hours=2)),
        },
        {
            "title": "Older",
            "published": format_datetime(datetime.now(UTC) - timedelta(days=1)),
        },
    ]

    assert derive_news_freshness_score(recent, stale_after_days=2) > 0.9


def test_news_coverage_uses_article_count_sufficiency() -> None:
    payload = [{"title": f"Story {index}"} for index in range(2)]

    assert derive_news_coverage_score(payload, minimum_items=10) == 0.2


def test_required_fields_coverage_uses_dataset_contract() -> None:
    payload = {
        "NIFTY_50": 24050.59,
        "INDIA_VIX": 18.85,
        "USD_INR": 93.02,
        "CRUDE_OIL": 98.77,
        "GOLD": 4782.10,
    }

    assert (
        derive_required_fields_coverage(
            payload,
            required_fields=[
                "NIFTY_50",
                "INDIA_VIX",
                "USD_INR",
                "CRUDE_OIL",
                "GOLD",
            ],
        )
        == 1.0
    )
