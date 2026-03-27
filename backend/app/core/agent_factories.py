"""Factory functions to create service instances for stateless agent nodes.

Replaces NodeResources singleton with dependency injection.
"""
from typing import Optional

from app.services.llama_cpp_service import LlamaCppService
from storage.sql.client import PostgresClient
from storage.vector.client import QdrantStorage
from data.providers.yfinance import YFinanceFetcher
from data.providers.rss_news import RSSNewsFetcher


class LLMServiceFactory:
    """Factory for creating LLM service instances."""
    
    _instance: Optional[LlamaCppService] = None
    
    @classmethod
    def get_llm_service(cls, model: str = "mistral-8b") -> LlamaCppService:
        """
        Get or create LLM service instance.
        
        Note: Model is passed to generate_message() calls, not stored here.
        This allows stateless nodes to specify which model to use.
        """
        if cls._instance is None:
            cls._instance = LlamaCppService()
        return cls._instance


class DataServiceFactory:
    """Factory for creating data service instances."""
    
    _sql_db: Optional[PostgresClient] = None
    _vector_db: Optional[QdrantStorage] = None
    _yf_fetcher: Optional[YFinanceFetcher] = None
    _rss_fetcher: Optional[RSSNewsFetcher] = None
    
    @classmethod
    def get_sql_db(cls) -> PostgresClient:
        if cls._sql_db is None:
            cls._sql_db = PostgresClient()
        return cls._sql_db
    
    @classmethod
    def get_vector_db(cls) -> QdrantStorage:
        if cls._vector_db is None:
            cls._vector_db = QdrantStorage()
        return cls._vector_db
    
    @classmethod
    def get_yf_fetcher(cls) -> YFinanceFetcher:
        if cls._yf_fetcher is None:
            cls._yf_fetcher = YFinanceFetcher()
        return cls._yf_fetcher
    
    @classmethod
    def get_rss_fetcher(cls) -> RSSNewsFetcher:
        if cls._rss_fetcher is None:
            cls._rss_fetcher = RSSNewsFetcher()
        return cls._rss_fetcher
