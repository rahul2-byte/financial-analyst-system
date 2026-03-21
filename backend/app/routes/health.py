from fastapi import APIRouter, Depends
from app.services.llama_cpp_service import LlamaCppService
from app.services.llm_interface import LLMServiceInterface
from app.config import settings

router = APIRouter()


def get_llm_service() -> LLMServiceInterface:
    return LlamaCppService()


@router.get("/health")
async def health_check(llm_service: LLMServiceInterface = Depends(get_llm_service)):
    """
    Checks the health of the API and its dependent services.
    - The LLM service health check will trigger the on-demand server start.
    """
    is_llm_up = await llm_service.check_health()

    status = "healthy" if is_llm_up else "degraded"

    return {
        "status": status,
        "services": {
            "llm_service": "up" if is_llm_up else "down",
            "llm_provider": "llama.cpp",
            "llm_server_url": settings.api.base_url,
        },
        "version": settings.API_VERSION,
    }
