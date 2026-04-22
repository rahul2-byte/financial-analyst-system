import logging
import json
import time
from collections import defaultdict, deque
from typing import List, AsyncGenerator, Any, Optional

from app.core.audit import (
    build_node_audit_entry,
    summarize_node_output,
    summarize_node_state,
)
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

    @staticmethod
    def _audit_safe_payload(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: PipelineOrchestrator._audit_safe_payload(subvalue)
                for key, subvalue in value.items()
                if key
                in {
                    "status",
                    "next_action",
                    "goal",
                    "plan_status",
                    "timeframe",
                    "approved_agents",
                    "tasks",
                    "task_contexts",
                    "errors",
                    "router_decision",
                    "data_check",
                }
            }
        if isinstance(value, list):
            return [
                PipelineOrchestrator._audit_safe_payload(item) for item in value[:5]
            ]
        return value

    @staticmethod
    def _audit_safe_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: PipelineOrchestrator._audit_safe_value(subvalue)
                for key, subvalue in list(value.items())[:10]
            }
        if isinstance(value, list):
            return [PipelineOrchestrator._audit_safe_value(item) for item in value[:5]]
        return value

    @staticmethod
    def _build_audit_context(
        base_state: Any,
        event_state: Any,
        output_payload: dict[str, Any],
    ) -> dict[str, Any]:
        context: dict[str, Any] = (
            dict(base_state) if isinstance(base_state, dict) else {}
        )
        if isinstance(event_state, dict):
            context.update(event_state)

        for key in ("goal", "timeframe", "iteration_count", "router_decision"):
            if (
                PipelineOrchestrator._is_missing_audit_context_value(
                    context.get(key), key
                )
                and key in output_payload
            ):
                context[key] = output_payload[key]

        return context

    @staticmethod
    def _is_missing_audit_context_value(value: Any, key: str) -> bool:
        if value is None:
            return True
        if key in {"timeframe", "router_decision"}:
            return not isinstance(value, str) or not value.strip()
        if key == "goal":
            return not isinstance(value, dict) or not value
        if key == "iteration_count":
            return value in {0, "", False}
        return False

    @staticmethod
    def _audit_log_data(
        node_name: str,
        output_payload: dict[str, Any],
        context_state: dict[str, Any],
    ) -> dict[str, Any]:
        audit_data = PipelineOrchestrator._audit_safe_payload(output_payload)
        output_data = output_payload.get("data")
        embedded_audit = (
            output_data.get("audit") if isinstance(output_data, dict) else None
        )

        audit_data["audit"] = (
            PipelineOrchestrator._audit_safe_value(embedded_audit)
            if isinstance(embedded_audit, dict)
            else build_node_audit_entry(node_name, context_state, output_payload)
        )
        return audit_data

    @staticmethod
    def _loop_snapshot(
        *,
        node_call_counts: dict[str, int],
        transition_counts: dict[str, int],
        transitions_recent: deque[str],
        last_state_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "node_call_counts": dict(sorted(node_call_counts.items())),
            "transition_counts": dict(sorted(transition_counts.items())),
            "last_transitions": list(transitions_recent),
            "state_snapshot": last_state_snapshot,
        }

    @staticmethod
    def _event_metadata(event: dict[str, Any]) -> dict[str, Any]:
        metadata = event.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        tags = event.get("tags")
        if not isinstance(tags, list):
            tags = []
        return {
            "event": event.get("event"),
            "name": event.get("name"),
            "run_id": event.get("run_id"),
            "parent_ids": event.get("parent_ids", []),
            "tags": tags[:10],
            "metadata": {str(k): metadata[k] for k in list(metadata.keys())[:10]},
        }

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
        session_logger.log_trace(
            "pipeline_invocation_start",
            {
                "query": scoped_query,
                "history_messages": len(conversation_history_dicts),
                "recursion_limit": 100,
            },
        )

        initial_state = build_initial_graph_state(
            user_query=scoped_query,
            conversation_history=conversation_history_dicts,
        )
        session_logger.log_trace(
            "initial_state_summary",
            summarize_node_state(initial_state),
        )

        node_call_counts: dict[str, int] = defaultdict(int)
        transition_counts: dict[str, int] = defaultdict(int)
        transitions_recent: deque[str] = deque(maxlen=20)
        last_state_snapshot: dict[str, Any] = summarize_node_state(initial_state)

        try:
            result = {}
            has_streamed_tokens = False
            node_start_ts: dict[tuple[str, int], float] = {}
            last_completed_node: str | None = None
            global_step_index = 0

            async for event in self.research_graph.astream_events(
                initial_state, version="v2", config={"recursion_limit": 100}
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

                if kind != "on_chat_model_stream":
                    session_logger.log_trace(
                        "graph_event",
                        {
                            "event_type": kind,
                            "meta": self._event_metadata(event),
                        },
                    )

                if kind in {"on_node_start", "on_chain_start"}:
                    node_name = event.get("name")
                    if not isinstance(node_name, str):
                        continue
                    if node_name == "LangGraph":
                        session_logger.log_trace(
                            "pipeline_chain_start",
                            {"meta": self._event_metadata(event)},
                        )
                        continue
                    event_data = event.get("data", {})
                    event_input = (
                        event_data.get("input")
                        if isinstance(event_data, dict)
                        else None
                    )
                    node_call_counts[node_name] += 1
                    global_step_index += 1
                    node_call_index = node_call_counts[node_name]
                    start_key = (node_name, node_call_index)
                    node_start_ts[start_key] = time.perf_counter()

                    transition = (
                        f"{last_completed_node}->{node_name}"
                        if last_completed_node
                        else f"START->{node_name}"
                    )
                    transition_counts[transition] += 1
                    transitions_recent.append(transition)

                    context_state = self._build_audit_context(
                        initial_state,
                        event_input,
                        {},
                    )
                    state_summary = summarize_node_state(context_state)
                    last_state_snapshot = state_summary
                    session_logger.log_trace(
                        "node_start",
                        {
                            "event": "node_start",
                            "node": node_name,
                            "node_call_index": node_call_index,
                            "global_step_index": global_step_index,
                            "iteration_count": int(
                                state_summary.get("iteration_count", 0) or 0
                            ),
                            "router_decision": state_summary.get("router_decision"),
                            "state_summary": state_summary,
                        },
                    )

                    # Skip internal langgraph nodes if needed, but for now show all
                    yield StreamEvent(
                        type="status", message=f"Pipeline processing: {node_name}..."
                    )

                elif kind in {"on_node_end", "on_chain_end"}:
                    node_name = event.get("name")
                    if not isinstance(node_name, str):
                        continue

                    if node_name == "LangGraph":
                        event_data = event.get("data", {})
                        output = (
                            event_data.get("output")
                            if isinstance(event_data, dict)
                            else None
                        )
                        if isinstance(output, dict):
                            result = output
                            context_state = self._build_audit_context(
                                initial_state,
                                (
                                    event_data.get("input")
                                    if isinstance(event_data, dict)
                                    else None
                                ),
                                output,
                            )
                            session_logger.log_step(
                                "PIPELINE_RESULT",
                                "LangGraph pipeline completed.",
                                parameters={
                                    "status": output.get("status"),
                                    "next_action": output.get("next_action"),
                                },
                                data=self._audit_log_data(
                                    "pipeline",
                                    output,
                                    context_state,
                                ),
                            )
                            session_logger.log_trace(
                                "pipeline_loop_snapshot",
                                {
                                    "event": "pipeline_loop_snapshot",
                                    **self._loop_snapshot(
                                        node_call_counts=node_call_counts,
                                        transition_counts=transition_counts,
                                        transitions_recent=transitions_recent,
                                        last_state_snapshot=last_state_snapshot,
                                    ),
                                },
                            )
                        continue

                    event_data = event.get("data", {})
                    output = (
                        event_data.get("output")
                        if isinstance(event_data, dict)
                        else None
                    )
                    output_payload = output if isinstance(output, dict) else {}
                    node_call_index = node_call_counts.get(node_name, 0)
                    start_key = (node_name, node_call_index)
                    duration_ms = None
                    if start_key in node_start_ts:
                        duration_ms = round(
                            (time.perf_counter() - node_start_ts.pop(start_key)) * 1000,
                            2,
                        )

                    context_state = self._build_audit_context(
                        initial_state,
                        (
                            event_data.get("input")
                            if isinstance(event_data, dict)
                            else None
                        ),
                        output_payload,
                    )
                    state_summary = summarize_node_state(context_state)
                    output_summary = summarize_node_output(output_payload)
                    last_state_snapshot = state_summary

                    session_logger.log_trace(
                        "node_end",
                        {
                            "event": "node_end",
                            "node": node_name,
                            "node_call_index": node_call_index,
                            "duration_ms": duration_ms,
                            "status": output_payload.get("status"),
                            "next_action": output_payload.get("next_action"),
                            "errors_count": len(output_payload.get("errors", []) or []),
                            "errors_preview": (output_payload.get("errors", []) or [])[
                                :3
                            ],
                            "router_decision": state_summary.get("router_decision"),
                            "state_summary": state_summary,
                            "output_summary": output_summary,
                        },
                    )

                    # Loop warning signal for repeated transitions.
                    if transitions_recent:
                        latest = transitions_recent[-1]
                        latest_count = transition_counts.get(latest, 0)
                        if latest_count >= 3:
                            session_logger.log_trace(
                                "loop_warning",
                                {
                                    "event": "loop_warning",
                                    "reason": "repeated_transition",
                                    "transition": latest,
                                    "repeat_count": latest_count,
                                    **self._loop_snapshot(
                                        node_call_counts=node_call_counts,
                                        transition_counts=transition_counts,
                                        transitions_recent=transitions_recent,
                                        last_state_snapshot=last_state_snapshot,
                                    ),
                                },
                            )

                    last_completed_node = node_name
                    session_logger.log_step(
                        f"NODE_{node_name.upper()}",
                        f"Node {node_name} completed.",
                        parameters={
                            "status": output_payload.get("status"),
                            "next_action": output_payload.get("next_action"),
                        },
                        data=self._audit_log_data(
                            node_name,
                            output_payload,
                            context_state,
                        ),
                    )

                elif kind in {"on_node_error", "on_chain_error"}:
                    node_name = event.get("name")
                    if not isinstance(node_name, str):
                        continue

                    if node_name == "LangGraph":
                        event_data = event.get("data", {})
                        session_logger.log_trace(
                            "pipeline_chain_error",
                            {
                                "error": (
                                    str(event_data.get("error"))
                                    if isinstance(event_data, dict)
                                    else "unknown_chain_error"
                                ),
                                "meta": self._event_metadata(event),
                            },
                        )
                        continue

                    event_data = event.get("data", {})
                    node_call_index = node_call_counts.get(node_name, 0)
                    start_key = (node_name, node_call_index)
                    duration_ms = None
                    if start_key in node_start_ts:
                        duration_ms = round(
                            (time.perf_counter() - node_start_ts.pop(start_key)) * 1000,
                            2,
                        )

                    raw_error = (
                        event_data.get("error")
                        if isinstance(event_data, dict)
                        else None
                    )
                    error_message = (
                        str(raw_error)
                        if raw_error is not None
                        else "unknown_node_error"
                    )

                    context_state = self._build_audit_context(
                        initial_state,
                        (
                            event_data.get("input")
                            if isinstance(event_data, dict)
                            else None
                        ),
                        {},
                    )
                    state_summary = summarize_node_state(context_state)
                    last_state_snapshot = state_summary

                    session_logger.log_trace(
                        "node_error",
                        {
                            "event": "node_error",
                            "node": node_name,
                            "node_call_index": node_call_index,
                            "duration_ms": duration_ms,
                            "error": error_message,
                            "router_decision": state_summary.get("router_decision"),
                            "state_summary": state_summary,
                        },
                    )

                    session_logger.log_step(
                        f"NODE_{node_name.upper()}_ERROR",
                        f"Node {node_name} failed.",
                        parameters={"error": error_message},
                        data={
                            "node": node_name,
                            "duration_ms": duration_ms,
                            "state_summary": state_summary,
                        },
                    )

                    last_completed_node = node_name

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

            final_report = result.get("final_report")
            final_output = result.get("final_output")
            errors_list = result.get("errors", [])

            if final_report or final_output:
                if not has_streamed_tokens:
                    primary_output = final_report if final_report else final_output
                    yield StreamEvent(
                        type="text_delta",
                        content=self._render_text_payload(primary_output),
                    )
                if isinstance(final_output, dict):
                    yield StreamEvent(type="final_payload", payload=final_output)
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
            loop_diagnostics = self._loop_snapshot(
                node_call_counts=node_call_counts,
                transition_counts=transition_counts,
                transitions_recent=transitions_recent,
                last_state_snapshot=last_state_snapshot,
            )
            session_logger.log_trace("pipeline_failure_diagnostics", loop_diagnostics)
            session_logger.log_error(
                "ORCHESTRATOR_ERROR",
                "The orchestrator encountered an error.",
                data={"exception": str(e), "loop_diagnostics": loop_diagnostics},
            )
            yield StreamEvent(
                type="error",
                message=f"An internal system error occurred: {str(e)}",
            )
