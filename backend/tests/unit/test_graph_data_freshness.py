from datetime import UTC, datetime, timedelta

from app.core.graph.nodes.autonomous_data_nodes import _derive_freshness_score


def test_freshness_score_is_high_for_recent_timestamp() -> None:
    recent = {"timestamp": (datetime.now(UTC) - timedelta(hours=2)).isoformat()}
    assert _derive_freshness_score(recent) > 0.9


def test_freshness_score_is_low_for_old_timestamp() -> None:
    old = {"timestamp": "2010-01-01T00:00:00+00:00"}
    assert _derive_freshness_score(old) < 0.2


def test_freshness_score_fallback_when_no_timestamp() -> None:
    payload = {"data": [1, 2, 3]}
    assert _derive_freshness_score(payload) == 0.5
