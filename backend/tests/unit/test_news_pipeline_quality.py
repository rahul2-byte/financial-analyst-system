from __future__ import annotations

from datetime import UTC, datetime, timedelta

from data.news_pipeline.quality import QualityScorer, SourceClassifier


def test_source_classifier_blocks_disallowed_domains():
    assert SourceClassifier.classify("zacks.com") == 4


def test_source_classifier_recognizes_upstox_published_news():
    assert SourceClassifier.classify("upstox.com") == 2


def test_quality_scorer_rewards_primary_sources_and_full_extraction():
    publish_time = datetime.now(UTC) - timedelta(days=1)

    score = QualityScorer.score(
        source_tier=1,
        extraction_status="full",
        publish_time=publish_time,
        relevance_check=True,
        word_count=400,
        is_duplicate=False,
    )

    assert score >= 40


def test_quality_scorer_penalizes_duplicates():
    publish_time = datetime.now(UTC)

    original = QualityScorer.score(
        source_tier=2,
        extraction_status="full",
        publish_time=publish_time,
        relevance_check=True,
        word_count=300,
        is_duplicate=False,
    )
    duplicate = QualityScorer.score(
        source_tier=2,
        extraction_status="full",
        publish_time=publish_time,
        relevance_check=True,
        word_count=300,
        is_duplicate=True,
    )

    assert duplicate < original
