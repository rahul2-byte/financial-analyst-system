"""Run the news pipeline independently and print redacted JSON diagnostics."""

from __future__ import annotations

import argparse
import asyncio
import json
import multiprocessing
from datetime import UTC, datetime
from queue import Empty
from typing import Any

from app.config import settings
from data.news_pipeline.connectors import TinyFishSearchConnector, UpstoxNewsConnector
from data.news_pipeline.extractor import ArticleExtractor
from data.news_pipeline.models import CompanyContext, ExtractionResult
from data.news_pipeline.runner import NewsPipelineRunner
from data.providers.upstox import UpstoxFetcher


class _SnippetExtractor:
    def extract(self, **kwargs: Any) -> ExtractionResult:
        snippet = str(kwargs.get("snippet") or "").strip() or None
        return ExtractionResult(
            article_text=snippet,
            word_count=len(snippet.split()) if snippet else 0,
            extraction_status="snippet_only",
            paywall_detected=False,
            relevance_check=bool(snippet),
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="HDFCBANK.NS")
    parser.add_argument("--company", default="HDFC Bank")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument(
        "--provider", choices=("tinyfish", "upstox", "all"), default="all"
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-article-fetch", action="store_true")
    parser.add_argument("--timeout", type=float, default=None)
    return parser


def _connectors(provider: str) -> list[Any]:
    connectors: list[Any] = []
    if provider in {"tinyfish", "all"}:
        connectors.append(TinyFishSearchConnector())
    if provider in {"upstox", "all"} and settings.UPSTOX_ACCESS_TOKEN:
        connectors.append(UpstoxNewsConnector(UpstoxFetcher()))
    return connectors


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    connectors = _connectors(args.provider)
    runner = NewsPipelineRunner(
        connectors=connectors,
        extractor=_SnippetExtractor() if args.no_article_fetch else ArticleExtractor(),
        total_timeout_seconds=args.timeout,
        allow_degraded_fallback=not args.strict,
    )
    company = CompanyContext(
        ticker=args.ticker,
        company_name=args.company,
        market="IN",
        nse_symbol=args.ticker.split(".", 1)[0],
    )
    started = datetime.now(UTC)
    records = await runner.run(company=company, time_window_days=args.days)
    return {
        "request": {
            "ticker": args.ticker,
            "company": args.company,
            "days": args.days,
            "provider": args.provider,
            "strict": args.strict,
            "article_fetch": not args.no_article_fetch,
        },
        "started_at": started.isoformat(),
        "stats": runner.last_run_stats,
        "connectors": [
            {
                "provider": type(connector).__name__,
                "stats": getattr(connector, "last_run_stats", {}),
            }
            for connector in connectors
        ],
        "records": [
            {
                "title": record.title,
                "url": record.url,
                "domain": record.source_domain,
                "provider": record.search_provider,
                "published": (
                    record.publish_time.isoformat() if record.publish_time else None
                ),
                "extraction_status": record.extraction_status,
                "word_count": record.word_count,
                "relevance": record.relevance_check,
                "quality_score": record.quality_score,
                "source_tier": record.source_tier,
                "duplicate": record.is_duplicate,
            }
            for record in records
        ],
    }


def _child_main(args: argparse.Namespace, result_queue: Any) -> None:
    async def run_and_report() -> None:
        result_queue.put(await _run(args))

    try:
        asyncio.run(run_and_report())
    except Exception as exc:  # noqa: BLE001 - diagnostic boundary
        result_queue.put({"error": f"{type(exc).__name__}: {exc}"})


def main() -> None:
    args = _parser().parse_args()
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    process = context.Process(target=_child_main, args=(args, result_queue))
    process.start()
    try:
        result = result_queue.get(
            timeout=(args.timeout or settings.NEWS_PIPELINE_TOTAL_TIMEOUT) + 10.0
        )
    except Empty:
        result = {"error": "diagnostic_process_timeout"}
    process.join(timeout=0.2)
    if process.is_alive():
        process.terminate()
        process.join()
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
