"""Small shared container for the two external services used by the graph."""


class NodeResources:
    """Singleton container for all resources with lazy initialization."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._llm_service = None
            self._yf_fetcher = None
            self._initialized = True

    @property
    def llm_service(self):
        if self._llm_service is None:
            from app.services.hive_service import HiveService

            self._llm_service = HiveService()
        return self._llm_service

    @property
    def yf_fetcher(self):
        if self._yf_fetcher is None:
            from data.providers.yfinance import YFinanceFetcher

            self._yf_fetcher = YFinanceFetcher()
        return self._yf_fetcher


resources = NodeResources()
