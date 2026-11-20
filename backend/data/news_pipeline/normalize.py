from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import timedelta
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


_TOKEN = re.compile(r"[a-z0-9&]+(?:[.,][0-9]+)*%?")
TITLE_SIMILARITY_THRESHOLD = 80.0


def _title_tokens(title: str) -> tuple[set[str], set[str]]:
    """Split a title into (word tokens, numeric tokens); numeric includes Q3, 12%."""
    words: set[str] = set()
    numbers: set[str] = set()
    for token in _TOKEN.findall(title.lower()):
        if any(char.isdigit() for char in token):
            numbers.add(token.replace(",", ""))
        else:
            words.add(token)
    return words, numbers


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
        except Exception:  # noqa: BLE001 - URL normalization fallback
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
            similarity = self._title_similarity(existing.title, candidate.title)
            if similarity >= TITLE_SIMILARITY_THRESHOLD:
                return index
        return None

    def _title_similarity(self, first: str, second: str) -> float:
        """Dice similarity of title token sets; 0 when numeric tokens differ.

        Titles that differ only in a number ("12%" vs "21%", "Q3" vs "Q4")
        describe different facts and must never be merged.
        """
        first_words, first_numbers = _title_tokens(first)
        second_words, second_numbers = _title_tokens(second)
        if first_numbers != second_numbers:
            return 0.0
        first_set = first_words | first_numbers
        second_set = second_words | second_numbers
        if not first_set or not second_set:
            return 0.0
        overlap = len(first_set & second_set)
        return 200.0 * overlap / (len(first_set) + len(second_set))

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
