import logging
import threading
from typing import List

from app.config import settings

# Conditional import to handle case where library isn't installed yet
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Singleton service to generate embeddings for text chunks using local models.
    """

    _instance = None

    # We recommend 'BAAI/bge-large-en-v1.5'
    def __new__(
        cls,
        model_name: str = "BAAI/bge-large-en-v1.5",
        idle_ttl_seconds: int | None = None,
    ):
        if cls._instance is None:
            cls._instance = super(EmbeddingService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        model_name: str = "BAAI/bge-large-en-v1.5",
        idle_ttl_seconds: int | None = None,
    ):
        if self._initialized:
            return

        self.model_name = model_name
        self.model = None
        self.idle_ttl_seconds = (
            int(settings.EMBEDDING_IDLE_TTL_SECONDS)
            if idle_ttl_seconds is None
            else idle_ttl_seconds
        )
        self._timer_factory = threading.Timer
        self._unload_timer: threading.Timer | None = None
        self._initialized = True

    @property
    def is_loaded(self) -> bool:
        return self.model is not None

    def _schedule_idle_unload(self) -> None:
        if self.idle_ttl_seconds <= 0:
            return

        if self._unload_timer is not None:
            self._unload_timer.cancel()

        timer = self._timer_factory(
            float(self.idle_ttl_seconds),
            lambda: self.unload_model(force=True),
        )
        if hasattr(timer, "daemon"):
            timer.daemon = True
        timer.start()
        self._unload_timer = timer

    def load_model(self):
        if self.model is None:
            if SentenceTransformer is None:
                raise ImportError(
                    "sentence-transformers is not installed. Please install it to use embeddings."
                )

            import os
            from pathlib import Path

            # Explicitly set the cache folder to the local project directory
            # so the model is only downloaded once and stored locally
            cache_dir = os.path.join(
                Path(__file__).parent.parent.parent, "ai-lab", "models", "embeddings"
            )
            os.makedirs(cache_dir, exist_ok=True)

            logger.info(
                f"Loading embedding model {self.model_name} from local folder: {cache_dir}..."
            )
            self.model = SentenceTransformer(self.model_name, cache_folder=cache_dir)
            logger.info("Embedding model loaded.")

        self._schedule_idle_unload()

    def embed_text(self, text: str) -> List[float]:
        """Generate an embedding for a single text string."""
        self.load_model()
        assert self.model is not None
        # The model returns a numpy array, we convert to list for pgvector/JSON
        embedding = self.model.encode(text)
        return embedding.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of text strings."""
        self.load_model()
        assert self.model is not None
        embeddings = self.model.encode(texts)
        return [emb.tolist() for emb in embeddings]

    def unload_model(self, *, force: bool = False):
        """Offload the model from memory to free up RAM/VRAM."""
        if not force and self.idle_ttl_seconds > 0:
            self._schedule_idle_unload()
            return

        if self._unload_timer is not None:
            self._unload_timer.cancel()
            self._unload_timer = None

        if self.model is not None:
            del self.model
            self.model = None

            import gc

            gc.collect()

            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

            logger.info("Embedding model offloaded from memory.")
