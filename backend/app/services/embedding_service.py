import logging
from typing import List

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

    # We recommend 'BAAI/bge-base-en-v1.5' or 'TaylorAI/bge-micro-financial'
    def __new__(cls, model_name: str = "TaylorAI/bge-micro-financial"):
        if cls._instance is None:
            cls._instance = super(EmbeddingService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = "TaylorAI/bge-micro-financial"):
        if self._initialized:
            return

        self.model_name = model_name
        self.model = None
        self._initialized = True

    def load_model(self):
        if self.model is None:
            if SentenceTransformer is None:
                raise ImportError(
                    "sentence-transformers is not installed. Please install it to use embeddings."
                )
            logger.info(f"Loading embedding model {self.model_name}...")
            self.model = SentenceTransformer(self.model_name)
            logger.info("Embedding model loaded.")

    def embed_text(self, text: str) -> List[float]:
        """Generate an embedding for a single text string."""
        self.load_model()
        # The model returns a numpy array, we convert to list for Qdrant/JSON
        embedding = self.model.encode(text)
        return embedding.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of text strings."""
        self.load_model()
        embeddings = self.model.encode(texts)
        return [emb.tolist() for emb in embeddings]
