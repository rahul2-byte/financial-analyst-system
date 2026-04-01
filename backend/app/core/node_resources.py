"""Provides a singleton container for all node resources (services, clients)."""


class NodeResources:
    """Singleton container for all resources with lazy initialization."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NodeResources, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._llm_service = None
            self._sql_db = None
            self._vector_db = None
            self._yf_fetcher = None
            self._rss_fetcher = None
            self._web_search = None
            self._initialized = True

    @property
    def llm_service(self):
        if self._llm_service is None:
            from app.services.llama_cpp_service import LlamaCppService

            self._llm_service = LlamaCppService()
        return self._llm_service

    @property
    def sql_db(self):
        if self._sql_db is None:
            from storage.sql.client import PostgresClient

            self._sql_db = PostgresClient()
        return self._sql_db

    @property
    def vector_db(self):
        if self._vector_db is None:
            from storage.vector.client import QdrantStorage

            self._vector_db = QdrantStorage()
        return self._vector_db

    @property
    def yf_fetcher(self):
        if self._yf_fetcher is None:
            from data.providers.yfinance import YFinanceFetcher

            self._yf_fetcher = YFinanceFetcher()
        return self._yf_fetcher

    @property
    def rss_fetcher(self):
        if self._rss_fetcher is None:
            from data.providers.rss_news import RSSNewsFetcher

            self._rss_fetcher = RSSNewsFetcher()
        return self._rss_fetcher

    @property
    def web_search(self):
        if self._web_search is None:
            from data.providers.web_search import WebSearchProvider

            self._web_search = WebSearchProvider()
        return self._web_search


resources = NodeResources()
