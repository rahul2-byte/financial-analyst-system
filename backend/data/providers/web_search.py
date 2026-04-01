from typing import List, Dict, Any, Optional
from ddgs import DDGS
import requests
from bs4 import BeautifulSoup
import logging
from app.core.observability import observe

logger = logging.getLogger(__name__)


class WebSearchProvider:
    """
    Provides internet search capabilities using DuckDuckGo and web scraping via BeautifulSoup.
    """

    def __init__(self):
        try:
            self.ddgs = DDGS(timeout=10)
        except TypeError:
            self.ddgs = DDGS()  # Fallback for older versions
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }

    @staticmethod
    def normalize_time_range(
        time_range: Optional[str], default: Optional[str] = "m"
    ) -> Optional[str]:
        """Normalizes timelimit values for DDGS to supported set: d, w, m, y."""
        if not time_range:
            return default

        normalized = str(time_range).strip().lower()
        if normalized in {"d", "w", "m", "y"}:
            return normalized

        aliases = {
            "day": "d",
            "daily": "d",
            "week": "w",
            "weekly": "w",
            "month": "m",
            "monthly": "m",
            "year": "y",
            "yearly": "y",
            "90d": "m",
            "d90": "m",
            "3m": "m",
            "last_90_days": "m",
        }
        return aliases.get(normalized, default)

    def search(
        self,
        query: str,
        max_results: int = 5,
        time_range: Optional[str] = "m",
        mode: str = "general",
    ) -> List[Dict[str, Any]]:
        """Unified search facade used by graph nodes."""
        normalized_mode = (mode or "general").strip().lower()
        if normalized_mode in {"news", "latest_news", "latest-news"}:
            return self.search_latest_news(
                query, max_results=max_results, time_range=time_range
            )
        return self.search_general_web(
            query, max_results=max_results, time_range=time_range
        )

    @observe(name="Tool:WebSearch:General")
    def search_general_web(
        self, query: str, max_results: int = 5, time_range: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform a standard text search on DuckDuckGo.
        time_range can be 'd' (day), 'w' (week), 'm' (month), 'y' (year).
        """
        try:
            # We can't use asyncio.wait_for directly here because it's synchronous code
            # But the orchestrator makes it async. Let's just catch exceptions from ddgs properly.
            # Actually ddgs text is synchronous generator, let's just make sure we capture it quickly.
            import time

            start = time.time()
            safe_time_range = self.normalize_time_range(time_range, default=None)
            results = []
            for r in self.ddgs.text(
                query, max_results=max_results, timelimit=safe_time_range
            ):
                results.append(r)
                if time.time() - start > 10.0:
                    logger.warning("Web search timed out, returning partial results")
                    break
            return results
        except Exception as e:
            logger.error(f"DuckDuckGo Search error: {e}")
            return [{"error": str(e)}]

    @observe(name="Tool:WebSearch:News")
    def search_latest_news(
        self, query: str, max_results: int = 5, time_range: Optional[str] = "w"
    ) -> List[Dict[str, Any]]:
        """
        Perform a news search on DuckDuckGo.
        """
        try:
            import time

            start = time.time()
            safe_time_range = self.normalize_time_range(time_range, default="w")
            results = []
            for r in self.ddgs.news(
                query, max_results=max_results, timelimit=safe_time_range
            ):
                results.append(r)
                if time.time() - start > 10.0:
                    logger.warning("News search timed out, returning partial results")
                    break
            return results
        except Exception as e:
            logger.error(f"DuckDuckGo News Search error: {e}")
            return [{"error": str(e)}]

    @observe(name="Tool:WebSearch:Scrape")
    def scrape_webpage(self, url: str) -> str:
        """
        Fetches a URL and extracts visible text using BeautifulSoup.
        Gracefully handles errors if scraping is blocked.
        """
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Remove scripts, styles, header, footer, nav
            for element in soup(
                ["script", "style", "header", "footer", "nav", "aside"]
            ):
                element.decompose()

            text = soup.get_text(separator="\n")

            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = "\n".join(chunk for chunk in chunks if chunk)

            # Limit the size to avoid overwhelming the LLM
            return text[:10000]
        except Exception as e:
            logger.error(f"Scraping error for {url}: {e}")
            return f"Failed to scrape {url}. Error: {str(e)}"
