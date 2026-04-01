from typing import List, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models
from data.interfaces.storage import IVectorStorage
from data.schemas.text import ProcessedChunk
from app.config import settings
import uuid
import math
from datetime import datetime


class QdrantStorage(IVectorStorage):
    def __init__(self):
        # Allow connecting via URI or defaulting to memory/local file for easy setup
        # If QDRANT_HOST is set, try to connect, otherwise use in-memory
        if hasattr(settings, "QDRANT_HOST") and settings.QDRANT_HOST:
            self.client = QdrantClient(
                host=settings.QDRANT_HOST, port=getattr(settings, "QDRANT_PORT", 6333)
            )
        else:
            # Fallback to local file or memory for dev
            self.client = QdrantClient(":memory:")

        self.collection_name = getattr(
            settings, "QDRANT_COLLECTION", "finance_knowledge"
        )
        self._ensure_collection()

    def _ensure_collection(self):
        collections = self.client.get_collections()
        exists = any(c.name == self.collection_name for c in collections.collections)

        if not exists:
            # Using 384 as default vector size for TaylorAI/bge-micro-financial / bge-small
            # Adjust if using bge-large (1024) or ada-002 (1536)
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=384, distance=models.Distance.COSINE
                ),
            )

            # Create full-text index on 'text' field for hybrid search
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="text",
                field_schema=models.TextIndexParams(
                    type="text",
                    tokenizer=models.TokenizerType.WORD,
                    min_token_len=2,
                    max_token_len=15,
                    lowercase=True,
                ),
            )

    def upsert_chunks(self, chunks: List[ProcessedChunk]) -> None:
        points = []
        for chunk in chunks:
            if not chunk.embedding:
                continue  # Skip chunks without embeddings for now

            points.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=chunk.embedding,
                    payload={
                        "text": chunk.text,
                        "ticker": chunk.ticker,
                        **chunk.metadata,
                    },
                )
            )

        if points:
            self.client.upsert(collection_name=self.collection_name, points=points)

    def hybrid_search(
        self,
        query_embedding: Optional[List[float]],
        query_text: str,
        limit: int = 5,
        ticker: Optional[str] = None,
    ) -> List[ProcessedChunk]:
        """
        Perform hybrid search using Reciprocal Rank Fusion (RRF) and Temporal Decay.
        """
        # 1. Vector Search (Top 20 candidates)
        vector_filter = None
        if ticker:
            vector_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="ticker", match=models.MatchValue(value=ticker)
                    )
                ]
            )

        vector_results = []
        if query_embedding:
            vector_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=vector_filter,
                limit=20,
            )

        # 2. Text/Keyword Search (Top 20 candidates)
        text_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="text", match=models.MatchText(text=query_text)
                )
            ]
        )
        if ticker:
            text_filter.must.append(
                models.FieldCondition(
                    key="ticker", match=models.MatchValue(value=ticker)
                )
            )

        text_results, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=text_filter,
            limit=20,
            with_payload=True,
            with_vectors=True,
        )

        # 3. Reciprocal Rank Fusion (RRF)
        # Score = 1 / (rank + 60)
        scores = {}  # point_id -> combined_rrf_score
        point_map = {}  # point_id -> result_object

        for rank, hit in enumerate(vector_results):
            scores[hit.id] = scores.get(hit.id, 0) + 1.0 / (rank + 1 + 60)
            point_map[hit.id] = hit

        for rank, point in enumerate(text_results):
            scores[point.id] = scores.get(point.id, 0) + 1.0 / (rank + 1 + 60)
            if point.id not in point_map:
                point_map[point.id] = point

        # 4. Temporal Decay
        # FinalScore = RRFScore * exp(-0.05 * days_old)
        now = datetime.now()
        final_results = []

        for point_id, rrf_score in scores.items():
            point = point_map[point_id]
            payload = point.payload or {}

            # Extract published_date from payload
            pub_date_str = payload.get("published_date")
            days_old = 0
            if pub_date_str:
                try:
                    # Attempt to parse ISO format
                    pub_date = datetime.fromisoformat(
                        pub_date_str.replace("Z", "+00:00")
                    )
                    days_old = (now - pub_date.replace(tzinfo=None)).days
                    if days_old < 0:
                        days_old = 0
                except (ValueError, TypeError):
                    days_old = 0

            decay = math.exp(-0.05 * days_old)
            final_score = rrf_score * decay
            final_results.append((point, final_score))

        # Sort by final score descending
        final_results.sort(key=lambda x: x[1], reverse=True)
        top_results = final_results[:limit]

        # Convert to ProcessedChunk
        chunks = []
        for point, score in top_results:
            payload = point.payload or {}
            chunks.append(
                ProcessedChunk(
                    chunk_id=str(point.id),
                    ticker=payload.get("ticker", "UNKNOWN"),
                    text=payload.get("text", ""),
                    metadata={str(k): str(v) for k, v in payload.items()},
                    embedding=getattr(point, "vector", None),
                )
            )
        return chunks

    def search(
        self,
        query_embedding: Optional[List[float]] = None,
        limit: int = 5,
        query_text: Optional[str] = None,
        ticker: Optional[str] = None,
    ) -> List[ProcessedChunk]:
        # Use hybrid search if query text is provided
        if query_text:
            return self.hybrid_search(query_embedding, query_text, limit, ticker)

        if not query_embedding:
            return []

        # Fallback to standard vector search
        vector_filter = None
        if ticker:
            vector_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="ticker", match=models.MatchValue(value=ticker)
                    )
                ]
            )

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            query_filter=vector_filter,
            limit=limit,
        )

        chunks = []
        for hit in results:
            payload = hit.payload or {}
            chunks.append(
                ProcessedChunk(
                    chunk_id=str(hit.id),
                    ticker=payload.get("ticker", "UNKNOWN"),
                    text=payload.get("text", ""),
                    metadata={str(k): str(v) for k, v in payload.items()},
                    embedding=hit.vector,
                )
            )
        return chunks
