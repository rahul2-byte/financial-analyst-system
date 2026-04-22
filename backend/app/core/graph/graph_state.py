from typing import TypedDict, Dict, Any, List, Optional, Annotated
import operator


def merge_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """Custom merge function for dicts - performs deep merge."""
    result = {**left}
    for key, value in right.items():
        if key in result:
            if isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = merge_dicts(result[key], value)
            elif isinstance(result[key], list) and isinstance(value, list):
                result[key] = result[key] + value
            else:
                result[key] = value
        else:
            result[key] = value
    return result


def replace_value(left: Any, right: Any) -> Any:
    """Overwrites the value with the new one (standard for single fields)."""
    return right


class ResearchGraphState(TypedDict):
    user_query: str
    conversation_history: List[Dict[str, str]]
    plan: Annotated[Optional[Dict[str, Any]], replace_value]
    executed_steps: Annotated[List[Dict[str, Any]], operator.add]
    agent_outputs: Annotated[Dict[str, Any], merge_dicts]
    tool_registry: Annotated[List[Dict[str, Any]], operator.add]
    draft_report: Annotated[Optional[str], replace_value]
    final_report: Annotated[Optional[str], replace_value]
    claim_verification: Annotated[Optional[Dict[str, Any]], replace_value]
    synthesis_retry_count: Annotated[int, replace_value]
    verification_retry_count: Annotated[int, replace_value]
    verification_passed: Annotated[bool, replace_value]
    verification_feedback: Annotated[Optional[str], replace_value]
    data_manifest: Annotated[Optional[Dict[str, Any]], replace_value]
    conflict_record: Annotated[Optional[Dict[str, Any]], replace_value]
    conflict_iteration_count: Annotated[int, replace_value]
    status: Annotated[Optional[str], replace_value]
    errors: Annotated[List[str], operator.add]
    retry_count: Annotated[int, replace_value]
    should_retry: Annotated[bool, replace_value]
    should_escalate: Annotated[bool, replace_value]
    failed_node: Annotated[Optional[str], replace_value]
    failed_step_number: Annotated[Optional[int], replace_value]
    current_step: Annotated[Optional[Dict[str, Any]], replace_value]
    selected_agents: Annotated[List[str], replace_value]
    plan_status: Annotated[Optional[str], replace_value]
    timeframe: Annotated[Optional[str], replace_value]
    timeframe_policy: Annotated[Dict[str, Any], merge_dicts]
    approved_agents: Annotated[List[str], replace_value]

    # Autonomous orchestration fields
    goal: Annotated[Optional[Dict[str, Any]], replace_value]
    hypotheses: Annotated[List[Dict[str, Any]], replace_value]
    data_status: Annotated[Dict[str, Any], merge_dicts]
    fetched_data: Annotated[Dict[str, Any], merge_dicts]
    data_check: Annotated[Dict[str, Any], merge_dicts]
    data_plan: Annotated[List[Dict[str, Any]], replace_value]
    tasks: Annotated[List[Dict[str, Any]], replace_value]
    task_contexts: Annotated[Dict[str, Any], replace_value]
    replanned_tasks: Annotated[List[Dict[str, Any]], replace_value]
    force_replan: Annotated[bool, replace_value]
    results: Annotated[Dict[str, Any], merge_dicts]

    # Confidence lifecycle
    synthesis_confidence: Annotated[float, replace_value]
    adjusted_confidence: Annotated[float, replace_value]
    smoothed_confidence: Annotated[float, replace_value]
    confidence_score: Annotated[float, replace_value]
    final_confidence: Annotated[float, replace_value]
    confidence_history: Annotated[List[float], replace_value]
    confidence_components: Annotated[Dict[str, Any], merge_dicts]

    # Routing and resilience
    critic_decision: Annotated[Optional[str], replace_value]
    router_decision: Annotated[Optional[str], replace_value]
    iteration_count: Annotated[int, replace_value]
    consecutive_research_plan_routes: Annotated[int, replace_value]
    retry_count_by_domain: Annotated[Dict[str, int], merge_dicts]
    freshness_policy: Annotated[Dict[str, Any], merge_dicts]
    evidence_strength: Annotated[float, replace_value]
    timeouts: Annotated[Dict[str, Any], merge_dicts]
    errors_detail: Annotated[List[Dict[str, Any]], operator.add]
    history: Annotated[List[Dict[str, Any]], operator.add]
    termination_reason: Annotated[Optional[str], replace_value]
    final_output: Annotated[Optional[Dict[str, Any]], replace_value]
    validation_passed: Annotated[bool, replace_value]
    evaluation_result: Annotated[Dict[str, Any], merge_dicts]
    evaluation_passed: Annotated[bool, replace_value]
    correction_prompt: Annotated[Optional[str], replace_value]
    intelligence_decision: Annotated[Dict[str, Any], merge_dicts]


def build_initial_graph_state(
    user_query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> ResearchGraphState:
    history = conversation_history or []
    return {
        "user_query": user_query,
        "conversation_history": history,
        "plan": None,
        "executed_steps": [],
        "agent_outputs": {},
        "tool_registry": [],
        "draft_report": None,
        "final_report": None,
        "claim_verification": None,
        "synthesis_retry_count": 0,
        "verification_retry_count": 0,
        "verification_passed": False,
        "verification_feedback": "",
        "data_manifest": None,
        "conflict_record": None,
        "conflict_iteration_count": 0,
        "status": "initializing",
        "errors": [],
        "retry_count": 0,
        "should_retry": False,
        "should_escalate": False,
        "failed_node": None,
        "failed_step_number": None,
        "current_step": None,
        "selected_agents": [],
        "plan_status": None,
        "timeframe": None,
        "timeframe_policy": {},
        "approved_agents": [],
        "goal": None,
        "hypotheses": [],
        "data_status": {},
        "fetched_data": {},
        "data_check": {},
        "data_plan": [],
        "tasks": [],
        "task_contexts": {},
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
        "consecutive_research_plan_routes": 0,
        "retry_count_by_domain": {},
        "freshness_policy": {},
        "evidence_strength": 0.0,
        "timeouts": {"task_timeout_s": 10.0, "stage_timeout_s": 20.0},
        "errors_detail": [],
        "history": [],
        "termination_reason": None,
        "final_output": None,
        "validation_passed": False,
        "evaluation_result": {},
        "evaluation_passed": False,
        "correction_prompt": None,
        "intelligence_decision": {},
    }
