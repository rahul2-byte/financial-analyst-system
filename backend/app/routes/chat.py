from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.models.request_models import ChatRequest
from app.core.orchestrator import PipelineOrchestrator
import json
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Single orchestrator instance for the app
orchestrator = PipelineOrchestrator()


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Chat endpoint. If the user asks a complex question, we route it through the Orchestrator.
    If it's simple chat, we stream it directly.
    For this version, we will pipe all user queries through the Orchestrator to utilize the agent tools.
    """
    try:
        # Extract the last user message
        user_query = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_query = msg.content
                break

        if not user_query:
            raise HTTPException(status_code=400, detail="No user message found.")

        logger.info(f"Processing query via Orchestrator: {user_query}")

        async def event_generator():
            try:
                async for event in orchestrator.execute_query(user_query):
                    yield f"data: {json.dumps(event)}\n\n"

                yield "data: [DONE]\n\n"
            except Exception as e_inner:
                logger.error(f"Error in event generator: {e_inner}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'content': str(e_inner)})}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)

        async def error_generator():
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(error_generator(), media_type="text/event-stream")
