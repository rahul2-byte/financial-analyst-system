import hashlib
import feedparser
from typing import Any, Dict, List
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

from app.core.observability import observe


TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ocid",
}


def normalize_article_url(url: str) -> str:
    if not url:
        return ""

    split_url = urlsplit(url.strip())
    query_params = [
        (key, value)
        for key, value in parse_qsl(split_url.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_PARAMS
    ]
    query_params.sort()
    normalized_path = split_url.path.rstrip("/") or "/"
    normalized_query = urlencode(query_params, doseq=True)

    return urlunsplit(
        (
            split_url.scheme.lower(),
            split_url.netloc.lower(),
            normalized_path,
            normalized_query,
            "",
        )
    )


def derive_article_hash(title: str, content: str) -> str:
    normalized_title = " ".join((title or "").split()).lower()
    normalized_content = " ".join((content or "").split()).lower()
    payload = f"{normalized_title}\n{normalized_content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def deduplicate_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduplicated: List[Dict[str, Any]] = []
    seen_canonical_urls: set[str] = set()
    seen_article_hashes: set[str] = set()

    for article in articles:
        normalized_article = dict(article)
        canonical_url = normalize_article_url(
            str(
                normalized_article.get("canonical_url")
                or normalized_article.get("link")
                or normalized_article.get("resolved_url")
                or normalized_article.get("original_url")
                or ""
            )
        )
        if canonical_url:
            if canonical_url in seen_canonical_urls:
                continue
            normalized_article["canonical_url"] = canonical_url

        article_hash = str(normalized_article.get("article_hash") or "").strip()
        if article_hash:
            if article_hash in seen_article_hashes:
                continue
            seen_article_hashes.add(article_hash)

        if canonical_url:
            seen_canonical_urls.add(canonical_url)

        deduplicated.append(normalized_article)

    return deduplicated


def enrich_article_with_body(article: Dict[str, Any], scraper: Any) -> Dict[str, Any]:
    enriched_article = dict(article)
    article_url = (
        enriched_article.get("canonical_url")
        or enriched_article.get("link")
        or enriched_article.get("resolved_url")
        or enriched_article.get("original_url")
        or ""
    )
    if not article_url or scraper is None:
        return enriched_article

    article_body = scraper.scrape_webpage(article_url).strip()
    if article_body and not article_body.startswith("Failed to scrape"):
        enriched_article["content"] = article_body
        enriched_article.setdefault(
            "article_hash",
            derive_article_hash(
                str(enriched_article.get("title", "")),
                article_body,
            ),
        )

    return enriched_article


class RSSNewsFetcher:
    FEEDS = {
        "general": "https://www.moneycontrol.com/rss/MCtopnews.xml",
        "markets": "https://www.moneycontrol.com/rss/marketreports.xml",
        "companies": "https://www.moneycontrol.com/rss/business.xml",
        "economy": "https://www.moneycontrol.com/rss/economy.xml",
    }

    def _search_feed_url(self, query: str, time_range: str | None = None) -> str:
        when_term = {
            "d": "1d",
            "w": "7d",
            "m": "30d",
            "y": "365d",
        }.get((time_range or "w").strip().lower(), "7d")
        terms = f"when:{when_term} site:moneycontrol.com {query.strip()}"
        return (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(terms)}&hl=en-IN&gl=IN&ceid=IN:en"
        )

    @observe(name="Tool:RSS:FetchMarketNews")
    def fetch_market_news(
        self,
        query: str = "general",
        limit: int = 10,
        time_range: str | None = None,
        include_body: bool = False,
        scraper: Any = None,
    ) -> List[Dict[str, Any]]:
        """Fetch news from predefined Indian market RSS feeds."""
        if query in self.FEEDS:
            feed_url = self.FEEDS[query]
        else:
            feed_url = self._search_feed_url(query or "general", time_range=time_range)
        parsed_feed = feedparser.parse(feed_url)

        results = []
        for entry in parsed_feed.entries[:limit]:
            article = {
                "title": entry.get("title", ""),
                "summary": entry.get("summary", entry.get("description", "")),
                "link": entry.get("link", ""),
                "url": entry.get("link", ""),
                "published": entry.get("published", entry.get("pubDate", "")),
                "published_date": entry.get("published", entry.get("pubDate", "")),
                "source": entry.get("source", {}).get("title", "Moneycontrol"),
            }
            article["canonical_url"] = normalize_article_url(article["link"])
            results.append(article)

        deduplicated_results = deduplicate_articles(results)
        if include_body and scraper is not None:
            enriched_results = [
                enrich_article_with_body(article, scraper)
                for article in deduplicated_results
            ]
            return deduplicate_articles(enriched_results)

        return deduplicated_results
