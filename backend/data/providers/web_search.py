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
        self.ddgs = DDGS()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }

    @observe(name="Tool:WebSearch:General")
    def search_general_web(
        self, query: str, max_results: int = 5, time_range: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform a standard text search on DuckDuckGo.
        time_range can be 'd' (day), 'w' (week), 'm' (month), 'y' (year).
        """
        try:
            results = self.ddgs.text(
                query,
                max_results=max_results,
                timelimit=time_range if time_range else None,
            )
            return list(results)
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
            results = self.ddgs.news(
                query,
                max_results=max_results,
                timelimit=time_range if time_range else None,
            )
            return list(results)
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
