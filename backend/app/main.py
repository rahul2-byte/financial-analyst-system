from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.core.logging import setup_logging
from app.core.llama_manager import llama_manager
from app.routes import chat, health

# --- OpenTelemetry Instrumentation ---
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

# Setup logging first
setup_logging(log_level="INFO" if not settings.DEBUG else "DEBUG")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic can go here if needed
    yield
    # Shutdown logic
    from app.core.observability import get_langfuse

    lf = get_langfuse()
    if lf:
        lf.flush()
    llama_manager.cleanup()


app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Instrument the app
if OTEL_AVAILABLE:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
        logger.info("FastAPI and HTTPX auto-instrumentation enabled.")
    except Exception as e:
        logger.error(f"Failed to instrument app: {e}")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global Exception Caught: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "message": str(exc)},
    )


# CORS Configuration
# Allow frontend to connect
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routes
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(health.router, prefix="/api", tags=["Health"])


@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.API_TITLE}", "docs": "/docs"}
