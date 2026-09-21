import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from app.config import settings
from app.core.logging import setup_logging
from app.core.prompts import PromptRegistry
from app.observability.tracing import initialize_tracing
from app.routes import health
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Setup logging first
setup_logging(log_level="INFO" if not settings.DEBUG else "DEBUG")
logger = logging.getLogger(__name__)
tracing = initialize_tracing()


@asynccontextmanager
async def lifespan(app: FastAPI):
    prompts = PromptRegistry.bundled()
    logger.info("prompt configuration loaded source=%s count=%d", prompts.source, len(prompts.keys()))
    app.state.prompt_registry = prompts
    try:
        yield
    finally:
        tracing.shutdown()


app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

if tracing.enabled:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, tracer_provider=tracing.provider)
    except Exception:
        logger.exception("FastAPI tracing instrumentation failed")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = uuid4().hex
    logger.exception(
        "Global exception caught request_id=%s path=%s", request_id, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal Server Error",
            "message": f"The request failed. Reference: {request_id}",
        },
    )


# Include Routes
app.include_router(health.router, prefix="/api", tags=["Health"])


@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.API_TITLE}", "docs": "/docs"}
