import logging
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.core.query_scope import normalize_research_scope
from app.services.hive_service import HiveService
from app.services.llm_interface import LLMServiceInterface
from data.news_pipeline.tinyfish_client import TinyFishSearchClient
from fastapi import APIRouter, Depends

router = APIRouter()
logger = logging.getLogger(__name__)


def get_llm_service() -> LLMServiceInterface:
    return HiveService()


def _check_market_data_readiness() -> bool:
    try:
        from data.providers.yfinance import YFinanceFetcher

        return YFinanceFetcher is not None
    except Exception:  # noqa: BLE001 - readiness must fail closed
        return False


async def _run_internal_canary() -> dict[str, object]:
    try:
        normalized_query = normalize_research_scope(
            "Analyze HDFC Bank for last one year with full deep analysis"
        )
        if not normalized_query:
            return {"status": "degraded", "details": {"query_normalization": "invalid"}}
        return {
            "status": "ok",
            "details": {
                "query_normalization": "ok",
                "runtime": "ok",
            },
        }
    except Exception:
        logger.exception("internal health canary failed")
        return {"status": "degraded", "details": {"query_normalization": "error"}}


async def _run_external_canary() -> dict[str, object]:
    if not settings.TINYFISH_API_KEY:
        return {
            "status": "degraded",
            "details": {"tinyfish_search": "missing_api_key"},
        }

    try:
        client = TinyFishSearchClient(api_key=str(settings.TINYFISH_API_KEY or ""))
        results = await client.search(
            query="HDFC Bank latest company news",
            num_results=1,
            start_published_date=datetime.now(UTC) - timedelta(days=7),
        )
        return {
            "status": "ok" if results else "degraded",
            "details": {"tinyfish_search": "ok" if results else "empty_results"},
        }
    except Exception:
        logger.exception("external health canary failed")
        return {"status": "degraded", "details": {"tinyfish_search": "error"}}


@router.get("/health")
async def health_check(
    llm_service: LLMServiceInterface = Depends(get_llm_service),  # noqa: B008
):
    """
    Checks the health of the API and its dependent services.
    - The LLM service health check will trigger the on-demand server start.
    """
    is_llm_up = await llm_service.check_health()
    is_market_data_ready = _check_market_data_readiness()
    internal_canary = await _run_internal_canary()
    external_canary = await _run_external_canary()

    core_healthy = all(
        (
            is_llm_up,
            is_market_data_ready,
            internal_canary.get("status") == "ok",
        )
    )
    status = "healthy" if core_healthy else "degraded"

    components = {
        "llm_service": "up" if is_llm_up else "down",
        "llm_provider": "hive",
        "llm_server_url": settings.HIVE_BASE_URL,
        "market_data": "up" if is_market_data_ready else "down",
        "tinyfish_search": "up" if settings.TINYFISH_API_KEY else "down",
    }

    return {
        "status": status,
        "services": components,
        "components": components,
        "canaries": {
            "internal": internal_canary,
            "external": external_canary,
        },
        "version": settings.API_VERSION,
    }
