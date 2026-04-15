from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import timedelta
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from data.news_pipeline.models import NewsPipelineRecord

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "ref",
    "source",
    "via",
    "mc_cid",
    "fbclid",
    "gclid",
}


class URLNormalizer:
    def normalize(self, url: str) -> str:
        parsed = urlparse(url)
        kept_params = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key not in TRACKING_PARAMS
        ]
        normalized_query = urlencode(sorted(kept_params))
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                normalized_query,
                "",
            )
        )

    def resolve_canonical(self, url: str) -> str:
        normalized = self.normalize(url)
        try:
            response = httpx.head(normalized, timeout=5.0, follow_redirects=True)
            response.raise_for_status()
            return self.normalize(str(response.url))
        except Exception:
            return normalized


class DuplicateDetector:
    def mark_duplicates(
        self, records: list[NewsPipelineRecord]
    ) -> list[NewsPipelineRecord]:
        deduped: list[NewsPipelineRecord] = []
        canonical_index: dict[str, int] = {}

        for record in records:
            canonical = record.canonical_url
            if canonical in canonical_index:
                existing_index = canonical_index[canonical]
                existing = deduped[existing_index]
                cluster_id = existing.cluster_id or self._cluster_id(existing, record)
                preferred, duplicate = self._prefer_more_complete(
                    existing, record, cluster_id
                )
                deduped[existing_index] = preferred
                deduped.append(duplicate)
                continue

            matched_index = self._find_fuzzy_duplicate(record, deduped)
            if matched_index is not None:
                existing = deduped[matched_index]
                cluster_id = existing.cluster_id or self._cluster_id(existing, record)
                preferred, duplicate = self._prefer_more_complete(
                    existing, record, cluster_id
                )
                deduped[matched_index] = preferred
                deduped.append(duplicate)
                canonical_index[preferred.canonical_url] = matched_index
                continue

            cluster_id = record.cluster_id or self._cluster_id(record)
            deduped.append(replace(record, is_duplicate=False, cluster_id=cluster_id))
            canonical_index[canonical] = len(deduped) - 1

        return deduped

    def _find_fuzzy_duplicate(
        self, candidate: NewsPipelineRecord, records: list[NewsPipelineRecord]
    ) -> int | None:
        for index, existing in enumerate(records):
            if existing.company_name != candidate.company_name:
                continue
            if not existing.publish_time or not candidate.publish_time:
                continue
            if abs(existing.publish_time - candidate.publish_time) > timedelta(
                hours=24
            ):
                continue
            if self._title_similarity(existing.title, candidate.title) >= 85:
                return index
        return None

    def _title_similarity(self, first: str, second: str) -> float:
        try:
            from rapidfuzz.fuzz import token_sort_ratio

            return float(token_sort_ratio(first, second))
        except Exception:
            normalized_first = " ".join(sorted(first.lower().split()))
            normalized_second = " ".join(sorted(second.lower().split()))
            return (
                SequenceMatcher(None, normalized_first, normalized_second).ratio()
                * 100.0
            )

    def _prefer_more_complete(
        self,
        left: NewsPipelineRecord,
        right: NewsPipelineRecord,
        cluster_id: str,
    ) -> tuple[NewsPipelineRecord, NewsPipelineRecord]:
        preferred = left
        duplicate = right
        if (right.word_count or 0) > (left.word_count or 0):
            preferred = right
            duplicate = left

        preferred = replace(preferred, is_duplicate=False, cluster_id=cluster_id)
        duplicate = replace(duplicate, is_duplicate=True, cluster_id=cluster_id)
        return preferred, duplicate

    def _cluster_id(self, *records: NewsPipelineRecord) -> str:
        basis = "|".join(
            record.canonical_url for record in records if record.canonical_url
        )
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
