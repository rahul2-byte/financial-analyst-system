import httpx
import json
import logging
import asyncio
from typing import AsyncGenerator, List, Dict, Any

from app.core.observability import observe, langfuse_context
from app.core.cache import cached_llm_response
from app.services.llm_interface import LLMServiceInterface
from app.models.request_models import Message
from app.config import settings
from app.core.llama_manager import llama_manager
from app.core.policies.retry_policy import MAX_RETRIES, exponential_backoff_seconds

logger = logging.getLogger(__name__)


class LlamaCppService(LLMServiceInterface):
    """
    Resilient service to interact with the llama.cpp server's OpenAI-compatible API.
    Features: Sequential request handling, exponential backoff retries for 500 errors.
    """

    def __init__(self):
        self.api_url = f"{str(settings.api.base_url).rstrip('/')}/v1/chat/completions"
        self.health_url = f"{str(settings.api.base_url).rstrip('/')}/health"

    async def check_health(self) -> bool:
        """Checks if the llama.cpp server is running and healthy."""
        try:
            await llama_manager.ensure_server_running()
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(self.health_url)
                return (
                    response.status_code == 200
                    and response.json().get("status") == "ok"
                )
        except Exception as e:
            logger.error(f"Llama.cpp server health check failed: {e}")
            return False

    @observe(name="LLM:Generate")
    async def generate(self, messages: List[Message], model: str, **kwargs) -> str:
        """Generates a complete response from the LLM with retry logic."""
        langfuse_context.update_current_observation(
            input=[msg.model_dump(exclude_none=True) for msg in messages],
            model=model,
            metadata={**kwargs, "llm_config": settings.llama_server.model_path},
        )

        payload = {
            "model": model,
            "messages": [msg.model_dump(exclude_none=True) for msg in messages],
            "stream": False,
            "max_tokens": kwargs.get("max_tokens", settings.model.max_output_tokens),
            "temperature": kwargs.get("temperature", 0.7),
        }
        if "response_format" in kwargs:
            payload["response_format"] = kwargs["response_format"]

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                await llama_manager.ensure_server_running()
                async with httpx.AsyncClient(timeout=settings.api.timeout) as client:
                    response = await client.post(
                        self.api_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )

                    if response.status_code == 200:
                        data = response.json()
                        content = (
                            data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        )
                        langfuse_context.update_current_observation(
                            as_type="generation",
                            output=content,
                            usage=data.get("usage"),
                            metadata={"stats_after": llama_manager.get_stats()},
                        )
                        return content

                    elif response.status_code == 500:
                        last_error = f"API 500: {response.text}"
                        logger.warning(
                            f"Llama.cpp 500 error (attempt {attempt+1}): {last_error}"
                        )
                        await asyncio.sleep(
                            exponential_backoff_seconds(attempt)
                        )  # Exponential backoff
                    else:
                        raise Exception(
                            f"Llama.cpp API Error: {response.status_code} - {response.text}"
                        )
            except Exception as e:
                last_error = str(e)
                logger.error(f"Error in Llama.cpp generate (attempt {attempt+1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(exponential_backoff_seconds(attempt))
                else:
                    raise Exception(
                        f"Failed after {MAX_RETRIES} attempts. Last error: {last_error}"
                    )

        return f"System Error: LLM request failed after retries. ({last_error})"

    @cached_llm_response(ttl=300)
    @observe(name="LLM:GenerateMessage")
    async def generate_message(
        self, messages: List[Message], model: str, **kwargs
    ) -> Message:
        """Generates a Message object (useful for tool calls) with retry logic."""
        langfuse_context.update_current_observation(
            input=[msg.model_dump(exclude_none=True) for msg in messages], model=model
        )

        payload = {
            "model": model,
            "messages": [msg.model_dump(exclude_none=True) for msg in messages],
            "stream": False,
            "max_tokens": kwargs.get("max_tokens", settings.model.max_output_tokens),
            "temperature": kwargs.get("temperature", 0.7),
        }
        if "response_format" in kwargs:
            payload["response_format"] = kwargs["response_format"]
        if "tools" in kwargs:
            payload["tools"] = kwargs["tools"]

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                await llama_manager.ensure_server_running()
                async with httpx.AsyncClient(timeout=settings.api.timeout) as client:
                    response = await client.post(
                        self.api_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )

                    if response.status_code == 200:
                        data = response.json()
                        msg_data = data.get("choices", [{}])[0].get("message", {})
                        langfuse_context.update_current_observation(
                            as_type="generation",
                            output=msg_data,
                            usage=data.get("usage"),
                        )
                        return Message(
                            role=msg_data.get("role", "assistant"),
                            content=msg_data.get("content"),
                            tool_calls=msg_data.get("tool_calls"),
                        )
                    elif response.status_code == 500:
                        last_error = f"API 500: {response.text}"
                        await asyncio.sleep(exponential_backoff_seconds(attempt))
                    else:
                        raise Exception(
                            f"Llama.cpp API Error: {response.status_code} - {response.text}"
                        )
            except Exception as e:
                last_error = str(e)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(exponential_backoff_seconds(attempt))
                else:
                    raise Exception(
                        f"Failed after {MAX_RETRIES} attempts. Last error: {last_error}"
                    )

        raise Exception(f"Failed after {MAX_RETRIES} attempts. Last error: {last_error}")

    def generate_stream(
        self, messages: List[Message], model: str, **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Generates a stream of tokens from the LLM."""

        async def generator():
            try:
                await llama_manager.ensure_server_running()
                payload = {
                    "model": model,
                    "messages": [msg.model_dump(exclude_none=True) for msg in messages],
                    "stream": True,
                    "max_tokens": kwargs.get(
                        "max_tokens", settings.model.max_output_tokens
                    ),
                    "temperature": kwargs.get("temperature", 0.7),
                }
                async with httpx.AsyncClient(timeout=settings.api.timeout) as client:
                    async with client.stream(
                        "POST",
                        self.api_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    ) as response:
                        if response.status_code != 200:
                            yield {
                                "event": "error",
                                "data": f"Provider Error: {response.status_code}",
                            }
                            return
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[len("data: ") :]
                                if data_str.strip() == "[DONE]":
                                    yield {"event": "done", "data": "[DONE]"}
                                    break
                                try:
                                    chunk = json.loads(data_str)
                                    content = (
                                        chunk.get("choices", [{}])[0]
                                        .get("delta", {})
                                        .get("content")
                                    )
                                    if content:
                                        yield {"event": "token", "data": content}
                                except json.JSONDecodeError:
                                    continue
            except Exception as e:
                logger.error(
                    f"Unexpected error in Llama.cpp stream: {e}", exc_info=True
                )
                yield {"event": "error", "data": str(e)}

        return generator()
