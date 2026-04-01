import asyncio
import logging
import random
from typing import List, AsyncGenerator, Any, Optional, Dict

from app.core.validators import sanitize_user_query, validate_query_not_malicious
from app.core.observability import langfuse_context
from app.core.logging import SessionLogger
from app.core.graph.graph_builder import get_research_graph
from app.models.request_models import Message
from app.models.response_models import StreamEvent

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """
    The central intelligence that executes the LangGraph research pipeline.
    """

    def __init__(self):
        self.research_graph = get_research_graph()

    # Disable @observe temporarily to fix "AsyncGenerator object is not callable" bug
    # @observe(name="Orchestrator:ExecuteQuery")
    async def execute_query(
        self,
        user_query: str,
        conversation_history: Optional[List[Message]] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Main entry point for handling a user query through the LangGraph pipeline."""
        yield StreamEvent(
            type="status",
            message="Initializing research pipeline...",
        )

        is_safe, reason = validate_query_not_malicious(user_query)
        if not is_safe:
            yield StreamEvent(
                type="error",
                message=f"Invalid input: {reason}",
            )
            return

        sanitized_query = sanitize_user_query(user_query)

        langfuse_context.update_current_trace(
            input=sanitized_query,
            tags=["orchestrator", "v1", "langgraph", "streaming"],
            user_id="anonymous",
            metadata={"source": "cli", "version": "v1.2"},
        )

        session_logger = SessionLogger.get_logger(sanitized_query)
        session_logger.log_step(
            "RECEIVE_QUERY",
            "New research query received by the orchestrator.",
            parameters={"query": sanitized_query},
        )

        def _normalize_message(msg) -> dict:
            """Normalize message to dict format."""
            if isinstance(msg, dict):
                return msg
            if hasattr(msg, "model_dump"):
                return msg.model_dump()
            return {"role": "unknown", "content": str(msg)}

        conversation_history_dicts = [
            _normalize_message(msg) for msg in (conversation_history or [])
        ]

        initial_state: Dict[str, Any] = {
            "user_query": sanitized_query,
            "conversation_history": conversation_history_dicts,
            "plan": None,
            "executed_steps": [],
            "agent_outputs": {},
            "tool_registry": [],
            "draft_report": None,
            "final_report": None,
            "data_manifest": None,
            "conflict_record": None,
            "conflict_iteration_count": 0,
            "status": "initializing",
            "synthesis_retry_count": 0,
            "verification_retry_count": 0,
            "verification_passed": False,
            "verification_feedback": "",
            "errors": [],
            "retry_count": 0,
            "should_retry": False,
            "should_escalate": False,
            "goal": None,
            "hypotheses": [],
            "data_status": {},
            "data_check": {},
            "data_plan": [],
            "tasks": [],
            "replanned_tasks": [],
            "force_replan": False,
            "results": {},
            "synthesis_confidence": 0.0,
            "adjusted_confidence": 0.0,
            "smoothed_confidence": 0.0,
            "confidence_score": 0.0,
            "final_confidence": 0.0,
            "confidence_history": [],
            "confidence_components": {},
            "critic_decision": None,
            "router_decision": None,
            "iteration_count": 0,
            "retry_count_by_domain": {},
            "freshness_policy": {},
            "evidence_strength": 0.0,
            "execution_budget": {},
            "timeouts": {"task_timeout_s": 10.0, "stage_timeout_s": 20.0},
            "errors_detail": [],
            "history": [],
            "termination_reason": None,
            "final_output": None,
            "validation_passed": False,
        }

        try:
            result = {}
            async for event in self.research_graph.astream_events(initial_state, version="v2"):
                kind = event["event"]
                
                if kind == "on_node_start":
                    node_name = event["name"]
                    # Skip internal langgraph nodes if needed, but for now show all
                    yield StreamEvent(
                        type="status",
                        message=f"Pipeline processing: {node_name}..."
                    )
                
                elif kind == "on_chat_model_stream":
                    # Capture streaming tokens from any node that uses streaming
                    content = event["data"]["chunk"].content
                    if content:
                        yield StreamEvent(
                            type="text_delta",
                            content=content
                        )
                
                elif kind == "on_chain_end":
                    if event["name"] == "LangGraph":
                        result = event["data"]["output"]

            final_output = result.get("final_output")
            errors_list = result.get("errors", [])
            plan = result.get("plan")

            if final_output:
                # If it wasn't already streamed (nodes currently use non-streaming generate_message)
                # we stream it here for UI consistency, but now we've already shown progress status
                async for event in self._stream_text(str(final_output)):
                    yield event
                yield StreamEvent(type="done")
                return

            if plan:
                response_mode = plan.get("response_mode")
                if response_mode:
                    mode_str = (
                        response_mode.value
                        if hasattr(response_mode, "value")
                        else str(response_mode)
                    )
                    if mode_str in [
                        "direct_response",
                        "ask_clarification",
                        "ask_plan_approval",
                    ]:
                        content = (
                            plan.get("proposed_plan")
                            if mode_str == "ask_plan_approval"
                            else plan.get("assistant_response")
                        )
                        if content:
                            async for event in self._stream_text(content):
                                yield event
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
                yield StreamEvent(
                    type="error", message="No report generated."
                )

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

    async def _stream_text(self, text: str) -> AsyncGenerator[StreamEvent, None]:
        """Streams text word-by-word with natural delay."""
        if not text:
            return

        words = text.split(" ")
        for i, word in enumerate(words):
            content = word + (" " if i < len(words) - 1 else "")
            yield StreamEvent(
                type="text_delta",
                content=content,
            )
            await asyncio.sleep(random.uniform(0.01, 0.04))
