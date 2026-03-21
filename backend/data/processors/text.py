from typing import List, Dict
from data.schemas.text import ProcessedChunk
from app.services.embedding_service import EmbeddingService
import uuid


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

    def chunk_text(
        self, text: str, metadata: Dict[str, str] = {}
    ) -> List[ProcessedChunk]:
        """
        Splits text into chunks recursively (Paragraph -> Sentence -> Word).
        This is a simplified implementation.
        """
        chunks = []
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
                        ticker=metadata.get("ticker", "UNKNOWN"),
                        text=chunk_text,
                        metadata=metadata,
                    )
                )

            # Move start forward, respecting overlap
            start = max(start + 1, end - self.chunk_overlap)

        return chunks

    def process_and_embed(
        self, text: str, metadata: Dict[str, str] = {}
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
