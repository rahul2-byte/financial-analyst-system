import asyncio
import logging
import random
from typing import List, AsyncGenerator, Any, Optional, Dict

from app.core.prompts import prompt_manager
from app.core.observability import observe, langfuse_context
from app.core.session_logging import SessionLogger
from app.core.graph_builder import build_graph

from app.models.request_models import Message
from app.models.response_models import StreamEvent

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """
    The central intelligence that executes the LangGraph research pipeline.
    """

    def __init__(self):
        self.research_graph = build_graph()

    @observe(name="Orchestrator:ExecuteQuery")
    async def execute_query(
        self,
        user_query: str,
        conversation_history: Optional[List[Message]] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Main entry point for handling a user query through the LangGraph pipeline."""
        yield StreamEvent(
            event="status",
            data={"message": "Initializing research pipeline..."},
        )

        langfuse_context.update_current_trace(
            input=user_query,
            tags=["orchestrator", "v1", "langgraph", "streaming"],
            user_id="anonymous",
            metadata={"source": "cli", "version": "v1.2"},
        )

        session_logger = SessionLogger.get_logger(user_query)
        session_logger.log_step(
            "RECEIVE_QUERY",
            "New research query received by the orchestrator.",
            parameters={"query": user_query},
        )

        conversation_history_dicts = [
            msg.model_dump() if hasattr(msg, "model_dump") else msg
            for msg in (conversation_history or [])
        ]

        initial_state: Dict[str, Any] = {
            "user_query": user_query,
            "conversation_history": conversation_history_dicts,
            "plan": None,
            "executed_steps": [],
            "agent_outputs": {},
            "tool_registry": [],
            "draft_report": None,
            "final_report": None,
            "synthesis_retry_count": 0,
            "verification_retry_count": 0,
            "verification_passed": False,
            "errors": [],
            "retry_count": 0,
            "should_retry": False,
            "should_escalate": False,
        }

        try:
            result = await self.research_graph.ainvoke(initial_state)

            final_report = result.get("final_report")
            errors_list = result.get("errors", [])
            plan = result.get("plan")

            if final_report:
                async for event in self._stream_text(final_report):
                    yield event
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
                            return

            if errors_list:
                error_msg = f"Pipeline failed: {'; '.join(errors_list)}"
                logger.error(error_msg)
                yield StreamEvent(
                    event="error",
                    data={"content": error_msg},
                )
            else:
                yield StreamEvent(
                    event="error", data={"content": "No report generated."}
                )

        except Exception as e:
            logger.error(f"Orchestrator failed: {e}", exc_info=True)
            session_logger.log_error(
                "ORCHESTRATOR_ERROR",
                "The orchestrator encountered an error.",
                data={"exception": str(e)},
            )
            yield StreamEvent(
                event="error",
                data={"content": f"An internal system error occurred: {str(e)}"},
            )

    async def _stream_text(self, text: str) -> AsyncGenerator[StreamEvent, None]:
        """Streams text word-by-word with natural delay."""
        if not text:
            return

        words = text.split(" ")
        for i, word in enumerate(words):
            content = word + (" " if i < len(words) - 1 else "")
            yield StreamEvent(
                event="token",
                data={"content": content},
            )
            await asyncio.sleep(random.uniform(0.01, 0.04))
