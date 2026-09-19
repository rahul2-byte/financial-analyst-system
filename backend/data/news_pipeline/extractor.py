from __future__ import annotations

import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

import httpx
from data.news_pipeline.models import ExtractionResult

logger = logging.getLogger(__name__)
MAX_ARTICLE_BYTES = 2_000_000

PAYWALL_PATTERNS = (
    "subscribe to read",
    "sign in to continue",
    "this content is for subscribers",
)


class ArticleExtractor:
    def extract(
        self,
        *,
        url: str,
        source_domain: str,
        company_name: str,
        ticker: str,
        snippet: str,
        source_type: str,
    ) -> ExtractionResult:
        article_text = None

        if url.lower().endswith(".pdf"):
            article_text = self._extract_pdf_text(url, max_pages=15)

        if not article_text:
            article_text = self._extract_with_trafilatura(url)

        extraction_status = "full"
        if not article_text:
            article_text = snippet or None
            extraction_status = "snippet_only"

        cleaned = self._clean_text(article_text)
        word_count = self._word_count(cleaned)
        paywall_detected = self._detect_paywall(cleaned)
        relevance_check = self._relevance_check(cleaned, company_name, ticker)

        if (
            extraction_status != "snippet_only"
            and source_type != "filing"
            and word_count < 100
        ):
            extraction_status = "partial"

        return ExtractionResult(
            article_text=cleaned,
            word_count=word_count,
            extraction_status=extraction_status,
            paywall_detected=paywall_detected,
            relevance_check=relevance_check,
        )

    def _extract_with_trafilatura(self, url: str) -> str | None:
        try:
            import trafilatura
        except ImportError:
            return None

        response = self._safe_get(url)
        if response is None:
            return None
        try:
            downloaded = response.text
            if not downloaded:
                return None
            return trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Trafilatura extraction failed for %s: %s", url, exc)
            return None

    def _extract_pdf_text(self, url: str, *, max_pages: int = 15) -> str | None:
        response = self._safe_get(url)
        if response is None:
            return None

        pdf_bytes = response.content
        return self._extract_with_pymupdf(pdf_bytes, max_pages=max_pages)

    def _safe_get(self, url: str) -> httpx.Response | None:
        current = url
        try:
            for _ in range(3):
                parsed = urlparse(current)
                if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                    return None
                addresses = socket.getaddrinfo(
                    parsed.hostname, 443 if parsed.scheme == "https" else 80
                )
                if any(
                    ipaddress.ip_address(item[4][0]).is_private
                    or ipaddress.ip_address(item[4][0]).is_loopback
                    for item in addresses
                ):
                    return None
                response = httpx.get(current, timeout=20.0, follow_redirects=False)
                if response.status_code in {301, 302, 303, 307, 308}:
                    current = response.headers.get("location", "")
                    continue
                response.raise_for_status()
                if len(response.content) > MAX_ARTICLE_BYTES:
                    return None
                return response
        except (OSError, httpx.HTTPError, ValueError) as exc:
            logger.warning("Article download failed: %s", exc)
        return None

    def _extract_with_pymupdf(self, pdf_bytes: bytes, *, max_pages: int) -> str | None:
        try:
            import fitz
        except ImportError:
            return None

        try:
            document = fitz.open(stream=pdf_bytes, filetype="pdf")
            try:
                pages = []
                for index in range(min(len(document), max_pages)):
                    page_text = document.load_page(index).get_text("text")
                    if page_text.strip():
                        pages.append(page_text)
                return "\n".join(pages).strip() or None
            finally:
                document.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("PyMuPDF extraction failed: %s", exc)
            return None

    def _clean_text(self, text: str | None) -> str | None:
        if not text:
            return text
        collapsed = re.sub(r"\s+", " ", text).strip()
        return collapsed or None

    def _word_count(self, text: str | None) -> int:
        if not text:
            return 0
        return len([token for token in text.split(" ") if token])

    def _detect_paywall(self, text: str | None) -> bool:
        if not text:
            return False
        lowered = text.lower()
        return any(pattern in lowered for pattern in PAYWALL_PATTERNS)

    def _relevance_check(
        self, text: str | None, company_name: str, ticker: str
    ) -> bool:
        if not text:
            return False
        lowered = text.lower()
        return company_name.lower() in lowered or ticker.lower() in lowered
