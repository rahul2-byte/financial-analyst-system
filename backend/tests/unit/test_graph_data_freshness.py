from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

from agents.shared.utils import derive_freshness_score


def test_freshness_score_is_high_for_recent_timestamp() -> None:
    recent = {"timestamp": (datetime.now(UTC) - timedelta(hours=2)).isoformat()}
    assert derive_freshness_score(recent) > 0.9


def test_freshness_score_is_low_for_old_timestamp() -> None:
    old = {"timestamp": "2010-01-01T00:00:00+00:00"}
    assert derive_freshness_score(old) < 0.2


def test_freshness_score_fallback_when_no_timestamp() -> None:
    payload = {"data": [1, 2, 3]}
    assert derive_freshness_score(payload) == 0.5


def test_freshness_score_uses_latest_rss_published_timestamp() -> None:
    recent = datetime.now(UTC) - timedelta(hours=2)
    older = datetime.now(UTC) - timedelta(days=5)
    payload = [
        {"title": "older", "published": format_datetime(older)},
        {"title": "recent", "published": format_datetime(recent)},
    ]

    assert derive_freshness_score(payload) > 0.9


def test_freshness_score_supports_fetched_at_metadata() -> None:
    payload = {
        "ticker": "HDFCBANK.NS",
        "marketCap": 123,
        "fetched_at": (datetime.now(UTC) - timedelta(minutes=15)).isoformat(),
    }

    assert derive_freshness_score(payload) > 0.9
