import re
from datetime import datetime
from typing import Dict, List, Any
import uuid

from app.services.embedding_service import EmbeddingService
from data.schemas.text import MetadataValue, ProcessedChunk


class TextProcessor:
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        use_embeddings: bool = True,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.use_embeddings = use_embeddings
        self.embedding_service = EmbeddingService() if use_embeddings else None

    @staticmethod
    def _serialize_metadata(
        metadata: Dict[str, object] | None,
    ) -> Dict[str, MetadataValue]:
        if not metadata:
            return {}

        serialized: Dict[str, MetadataValue] = {}
        for key, value in metadata.items():
            if isinstance(value, datetime):
                serialized[key] = value.isoformat()
            elif isinstance(value, (str, int, float, bool)) or value is None:
                serialized[key] = value
            else:
                raise TypeError(f"Unsupported metadata value for '{key}'")
        return serialized

    @staticmethod
    def _require_ticker(metadata: Dict[str, MetadataValue]) -> str:
        ticker = metadata.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError("metadata must include a non-empty ticker")
        return ticker

    @staticmethod
    def clean_text(text: str) -> str:
        if not text:
            return ""

        # 1. Remove URLs
        text = re.sub(
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            "",
            text,
        )

        # 2. Remove Markdown headers (###, #####, etc.)
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)

        # 3. Remove common share/nav boilerplate
        boilerplate_patterns = [
            r"WhatsApp X Facebook LinkedIn Messenger Reddit Mail",
            r"Updated - .*",
            r"Published on .*",
            r"READ MORE",
        ]
        for pattern in boilerplate_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # 4. Remove excessive newlines and whitespace
        # Replace 3 or more newlines with exactly 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Remove leading/trailing whitespace on each line
        text = "\n".join([line.strip() for line in text.splitlines() if line.strip()])

        return text.strip()

    def chunk_text(
        self, text: str, metadata: Dict[str, object] | None = None
    ) -> List[ProcessedChunk]:
        """
        Splits text into chunks recursively (Paragraph -> Sentence -> Word).
        This is a simplified implementation.
        """
        text = self.clean_text(text)
        chunks = []
        serialized_metadata = self._serialize_metadata(metadata)
        ticker = self._require_ticker(serialized_metadata)
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + self.chunk_size

            # If end is not at the end of text, try to find a sentence break
            if end < text_len:
                # Look for last period, newline, or space within overlap window
                # Prioritize Newline -> Period -> Space
                segment = text[start:end]

                # Check for paragraph break
                newline_idx = segment.rfind("\n")
                if newline_idx != -1 and newline_idx > (
                    self.chunk_size - self.chunk_overlap
                ):
                    end = start + newline_idx + 1
                else:
                    # Check for sentence break
                    period_idx = segment.rfind(". ")
                    if period_idx != -1 and period_idx > (
                        self.chunk_size - self.chunk_overlap
                    ):
                        end = start + period_idx + 1
                    else:
                        # Fallback to space
                        space_idx = segment.rfind(" ")
                        if space_idx != -1 and space_idx > (
                            self.chunk_size - self.chunk_overlap
                        ):
                            end = start + space_idx + 1

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    ProcessedChunk(
                        chunk_id=str(uuid.uuid4()),
                        ticker=ticker,
                        text=chunk_text,
                        metadata=serialized_metadata,
                    )
                )

            # Move start forward, respecting overlap
            start = max(start + 1, end - self.chunk_overlap)

        return chunks

    def process_and_embed(
        self, text: str, metadata: Dict[str, object] | None = None
    ) -> List[ProcessedChunk]:
        """Chunks text and applies embeddings to each chunk."""
        chunks = self.chunk_text(text, metadata)

        if self.use_embeddings and self.embedding_service and chunks:
            texts_to_embed = [chunk.text for chunk in chunks]
            try:
                embeddings = self.embedding_service.embed_batch(texts_to_embed)
                for i, chunk in enumerate(chunks):
                    if i < len(embeddings):
                        chunk.embedding = embeddings[i]
            except ImportError:
                import logging

                logging.getLogger(__name__).warning(
                    "Embeddings skipped because sentence-transformers is not installed."
                )

        return chunks


RELEVANCE_FREQUENCY_THRESHOLD = 3
RELEVANCE_LEAD_CHARS = 500


def is_article_relevant(
    article: Dict[str, Any],
    ticker: str,
    company_name: str | None = None,
    adr_aliases: List[str] | None = None,
    lenient: bool = False,
) -> bool:
    """
    Evaluates if an article is relevant to the target ticker or company.

    Checks:
    1. Ticker or company name in title.
    2. Ticker or company name in the first 500 characters of content.
    3. Minimum frequency of ticker/company name in the full text.
       (Skipped in lenient mode for top-ranked results.)

    Args:
        article: Article dict with 'title' and 'content' keys.
        ticker: Primary ticker symbol (e.g., "HDFC").
        company_name: Full company name (e.g., "HDFC Bank").
        adr_aliases: Optional list of ADR ticker aliases (e.g., ["HDB"]).
        lenient: If True, skip frequency threshold check; require title or lead
                  content match only. Use for top-ranked search results.
    """
    title = str(article.get("title", "")).strip()
    content = str(article.get("content", "")).strip()

    if not title and not content:
        return False

    targets = [ticker]
    if company_name:
        targets.append(company_name)
    if adr_aliases:
        for alias in adr_aliases:
            if alias and str(alias).strip():
                targets.append(str(alias).strip())

    valid_targets = [str(t) for t in targets if t and str(t).strip()]
    if not valid_targets:
        return False

    patterns = [
        re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE) for t in valid_targets
    ]

    if title:
        for pattern in patterns:
            if pattern.search(title):
                return True

    if content:
        lead_content = content[:RELEVANCE_LEAD_CHARS]
        for pattern in patterns:
            if pattern.search(lead_content):
                return True

        if lenient:
            return False

        total_count = 0
        for pattern in patterns:
            total_count += len(pattern.findall(content))

        if total_count >= RELEVANCE_FREQUENCY_THRESHOLD:
            return True

    return False
