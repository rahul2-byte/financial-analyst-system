import feedparser
from typing import List, Dict, Any
from app.core.observability import observe


class RSSNewsFetcher:
    FEEDS = {
        "general": "https://www.moneycontrol.com/rss/MCtopnews.xml",
        "markets": "https://www.moneycontrol.com/rss/marketreports.xml",
        "companies": "https://www.moneycontrol.com/rss/business.xml",
        "economy": "https://www.moneycontrol.com/rss/economy.xml",
    }

    @observe(name="Tool:RSS:FetchMarketNews")
    def fetch_market_news(
        self, category: str = "general", limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Fetch news from predefined Indian market RSS feeds."""
        if category not in self.FEEDS:
            category = "general"

        feed_url = self.FEEDS[category]
        parsed_feed = feedparser.parse(feed_url)

        results = []
        for entry in parsed_feed.entries[:limit]:
            results.append(
                {
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                }
            )

        return results
