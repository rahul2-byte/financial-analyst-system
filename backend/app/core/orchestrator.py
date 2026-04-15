import logging
import json
from typing import List, AsyncGenerator, Any, Optional

from app.core.intent_classifier import (
    NON_FINANCIAL_FALLBACK_RESPONSE,
    classify_query_intent,
)
from app.core.query_scope import normalize_research_scope
from app.core.validators import sanitize_user_query, validate_query_not_malicious
from app.core.observability import langfuse_context
from app.core.logging import SessionLogger
from app.core.graph.graph_state import build_initial_graph_state
from app.core.graph.runtime.graph_builder import get_research_graph
from app.models.request_models import Message
from app.models.response_models import StreamEvent

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """
    The central intelligence that executes the LangGraph research pipeline.
    """

    def __init__(self):
        self.research_graph = get_research_graph()

    @staticmethod
    def _normalize_message(msg: Any) -> dict[str, Any]:
        if isinstance(msg, dict):
            return msg
        if hasattr(msg, "model_dump"):
            return msg.model_dump()
        return {"role": "unknown", "content": str(msg)}

    @staticmethod
    def _render_text_payload(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=True)
        return str(value)

    async def execute_query(
        self,
        user_query: str,
        conversation_history: Optional[List[Message]] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Main entry point for handling a user query through the LangGraph pipeline."""
        is_safe, reason = validate_query_not_malicious(user_query)
        if not is_safe:
            yield StreamEvent(
                type="error",
                message=f"Invalid input: {reason}",
            )
            return

        sanitized_query = sanitize_user_query(user_query)
        scoped_query = normalize_research_scope(sanitized_query)

        conversation_history_dicts = [
            self._normalize_message(msg) for msg in (conversation_history or [])
        ]

        try:
            intent = await classify_query_intent(
                sanitized_query,
                conversation_history_dicts,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Intent classification failed: %s", exc, exc_info=True)
            intent = None

        if intent is None or not intent.is_financial_request:
            response_text = (
                intent.assistant_response
                if intent and intent.assistant_response
                else NON_FINANCIAL_FALLBACK_RESPONSE
            )
            yield StreamEvent(type="text_delta", content=response_text)
            yield StreamEvent(type="done")
            return

        yield StreamEvent(
            type="status",
            message="Initializing research pipeline...",
        )

        langfuse_context.update_current_trace(
            input=sanitized_query,
            tags=["orchestrator", "v1", "langgraph", "streaming"],
            user_id="anonymous",
            metadata={"source": "cli", "version": "v1.2"},
        )

        session_logger = SessionLogger.get_logger(scoped_query)
        session_logger.log_step(
            "RECEIVE_QUERY",
            "New research query received by the orchestrator.",
            parameters={"query": scoped_query},
        )

        initial_state = build_initial_graph_state(
            user_query=scoped_query,
            conversation_history=conversation_history_dicts,
        )

        try:
            result = {}
            has_streamed_tokens = False
            async for event in self.research_graph.astream_events(
                initial_state, version="v2"
            ):
                if not isinstance(event, dict):
                    logger.warning(
                        "Skipping non-dict graph event", extra={"event": str(event)}
                    )
                    continue

                kind = event.get("event")
                if not isinstance(kind, str):
                    logger.warning(
                        "Skipping malformed graph event", extra={"event": event}
                    )
                    continue

                if kind == "on_node_start":
                    node_name = event.get("name")
                    if not isinstance(node_name, str):
                        continue
                    # Skip internal langgraph nodes if needed, but for now show all
                    yield StreamEvent(
                        type="status", message=f"Pipeline processing: {node_name}..."
                    )

                elif kind == "on_chat_model_stream":
                    # Capture streaming tokens from any node that uses streaming
                    chunk = event.get("data", {}).get("chunk")
                    content = getattr(chunk, "content", None)
                    if content:
                        has_streamed_tokens = True
                        yield StreamEvent(
                            type="text_delta",
                            content=self._render_text_payload(content),
                        )

                elif kind == "on_chain_end":
                    if event.get("name") == "LangGraph":
                        output = event.get("data", {}).get("output")
                        if isinstance(output, dict):
                            result = output

            final_output = result.get("final_output")
            errors_list = result.get("errors", [])

            if final_output:
                if not has_streamed_tokens:
                    yield StreamEvent(
                        type="text_delta",
                        content=self._render_text_payload(final_output),
                    )
                yield StreamEvent(type="done")
                return

            if errors_list:
                error_msg = f"Pipeline failed: {'; '.join(errors_list)}"
                logger.error(error_msg)
                yield StreamEvent(
                    type="error",
                    message=error_msg,
                )
            else:
                yield StreamEvent(type="error", message="No report generated.")

        except Exception as e:
            logger.error(f"Orchestrator failed: {e}", exc_info=True)
            session_logger.log_error(
                "ORCHESTRATOR_ERROR",
                "The orchestrator encountered an error.",
                data={"exception": str(e)},
            )
            yield StreamEvent(
                type="error",
                message=f"An internal system error occurred: {str(e)}",
            )
