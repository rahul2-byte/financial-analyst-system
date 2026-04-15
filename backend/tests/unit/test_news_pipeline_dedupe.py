from __future__ import annotations

from datetime import UTC, datetime

from data.news_pipeline.models import NewsPipelineRecord
from data.news_pipeline.normalize import DuplicateDetector, URLNormalizer


def test_url_normalizer_strips_tracking_parameters():
    normalizer = URLNormalizer()

    normalized = normalizer.normalize(
        "https://example.com/story?utm_source=rss&ref=abc&id=1&utm_medium=email"
    )

    assert normalized == "https://example.com/story?id=1"


def test_duplicate_detector_clusters_similar_titles_same_day():
    detector = DuplicateDetector()
    publish_time = datetime(2026, 4, 12, 10, 0, tzinfo=UTC)

    records = [
        NewsPipelineRecord(
            ticker="RELIANCE",
            company_name="Reliance Industries",
            market="IN",
            url="https://example.com/a",
            canonical_url="https://example.com/a",
            title="Reliance board approves fundraising plan",
            author=None,
            snippet="",
            article_text="Reliance Industries announced a fundraising plan. " * 30,
            word_count=180,
            publish_time=publish_time,
            retrieval_time=publish_time,
            source_domain="example.com",
            source_type="rss",
            source_tier=2,
            paywall_detected=False,
            extraction_status="full",
            quality_score=60,
            relevance_check=True,
            is_duplicate=False,
            cluster_id=None,
            query_intent="strategic",
            search_provider="rss",
            pipeline_version="1.0.0",
        ),
        NewsPipelineRecord(
            ticker="RELIANCE",
            company_name="Reliance Industries",
            market="IN",
            url="https://example.com/b",
            canonical_url="https://example.com/b",
            title="Reliance approves fundraising plan at board meeting",
            author=None,
            snippet="",
            article_text="Reliance Industries approved the plan. " * 10,
            word_count=60,
            publish_time=publish_time,
            retrieval_time=publish_time,
            source_domain="example.com",
            source_type="rss",
            source_tier=2,
            paywall_detected=False,
            extraction_status="partial",
            quality_score=40,
            relevance_check=True,
            is_duplicate=False,
            cluster_id=None,
            query_intent="strategic",
            search_provider="rss",
            pipeline_version="1.0.0",
        ),
    ]

    deduped = detector.mark_duplicates(records)

    assert deduped[0].is_duplicate is False
    assert deduped[1].is_duplicate is True
    assert deduped[0].cluster_id == deduped[1].cluster_id
