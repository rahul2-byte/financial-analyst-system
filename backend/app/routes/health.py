from app.config import settings
from app.core.graph.graph_state import build_initial_graph_state
from app.core.query_scope import normalize_research_scope
from app.services import embedding_service as embedding_service_module
from app.services.embedding_service import EmbeddingService
from app.services.llama_cpp_service import LlamaCppService
from app.services.llm_interface import LLMServiceInterface
from data.news_pipeline.exa_client import ExaSearchClient
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from storage.sql.client import PostgresClient

router = APIRouter()


def get_llm_service() -> LLMServiceInterface:
    return LlamaCppService()


def _check_database_readiness() -> bool:
    try:
        return PostgresClient().is_db_up()
    except Exception:
        return False


def _check_embedding_readiness() -> bool:
    try:
        service = EmbeddingService()
        return (
            service.is_loaded
            or embedding_service_module.SentenceTransformer is not None
        )
    except Exception:
        return False


async def _run_internal_canary() -> dict[str, object]:
    try:
        query = normalize_research_scope(
            "Analyze HDFC Bank for last one year with full deep analysis"
        )
        state = build_initial_graph_state(user_query=query, conversation_history=[])
        if not isinstance(state, dict):
            return {"status": "degraded", "details": {"graph_state": "invalid"}}
        return {
            "status": "ok",
            "details": {
                "query_normalization": "ok",
                "graph_state": "ok",
            },
        }
    except Exception as exc:
        return {"status": "degraded", "details": {"error": str(exc)}}


async def _run_external_canary() -> dict[str, object]:
    if not settings.EXA_API_KEY:
        return {"status": "degraded", "details": {"exa_search": "missing_api_key"}}

    try:
        client = ExaSearchClient(api_key=str(settings.EXA_API_KEY or ""))
        results = await client.search(
            query="HDFC Bank latest company news",
            num_results=1,
            start_published_date=datetime.now(timezone.utc) - timedelta(days=7),
        )
        return {
            "status": "ok" if results else "degraded",
            "details": {"exa_search": "ok" if results else "empty_results"},
        }
    except Exception as exc:
        return {"status": "degraded", "details": {"error": str(exc)}}


@router.get("/health")
async def health_check(llm_service: LLMServiceInterface = Depends(get_llm_service)):
    """
    Checks the health of the API and its dependent services.
    - The LLM service health check will trigger the on-demand server start.
    """
    is_llm_up = await llm_service.check_health()
    is_db_up = _check_database_readiness()
    is_embedding_ready = _check_embedding_readiness()
    internal_canary = await _run_internal_canary()
    external_canary = await _run_external_canary()

    core_healthy = all(
        (
            is_llm_up,
            is_db_up,
            is_embedding_ready,
            internal_canary.get("status") == "ok",
        )
    )
    status = "healthy" if core_healthy else "degraded"

    components = {
        "llm_service": "up" if is_llm_up else "down",
        "llm_provider": "llama.cpp",
        "llm_server_url": settings.api.base_url,
        "database": "up" if is_db_up else "down",
        "embedding_service": "up" if is_embedding_ready else "down",
        "exa_search": "up" if settings.EXA_API_KEY else "down",
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
