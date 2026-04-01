from typing import TypedDict, Dict, Any, List, Optional, Annotated
import operator


def merge_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """Custom merge function for dicts - performs deep merge."""
    result = {**left}
    for key, value in right.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


class ResearchGraphState(TypedDict):
    user_query: str
    conversation_history: List[Dict[str, str]]
    plan: Optional[Dict[str, Any]]
    executed_steps: Annotated[List[Dict[str, Any]], operator.add]
    agent_outputs: Annotated[Dict[str, Any], merge_dicts]
    tool_registry: Annotated[List[Dict[str, Any]], operator.add]
    draft_report: Optional[str]
    final_report: Optional[str]
    synthesis_retry_count: int
    verification_retry_count: int
    verification_passed: bool
    errors: Annotated[List[str], operator.add]
    retry_count: int
    should_retry: bool
    should_escalate: bool

    # Autonomous orchestration state
    goal: Optional[Dict[str, Any]]
    hypotheses: List[Dict[str, Any]]
    data_status: Annotated[Dict[str, Any], merge_dicts]
    data_plan: List[Dict[str, Any]]
    tasks: List[Dict[str, Any]]
    results: Annotated[Dict[str, Any], merge_dicts]

    # Confidence lifecycle
    synthesis_confidence: float
    adjusted_confidence: float
    smoothed_confidence: float
    confidence_score: float
    final_confidence: float
    confidence_history: List[float]
    confidence_components: Annotated[Dict[str, Any], merge_dicts]

    # Router and control-plane
    critic_decision: Optional[str]
    router_decision: Optional[str]
    iteration_count: int
    retry_count_by_domain: Annotated[Dict[str, int], merge_dicts]

    # Robustness and policy controls
    freshness_policy: Annotated[Dict[str, Any], merge_dicts]
    evidence_strength: float
    execution_budget: Annotated[Dict[str, Any], merge_dicts]
    timeouts: Annotated[Dict[str, Any], merge_dicts]
    errors_detail: Annotated[List[Dict[str, Any]], operator.add]
    history: Annotated[List[Dict[str, Any]], operator.add]

    # Output lifecycle
    termination_reason: Optional[str]
    final_output: Optional[Dict[str, Any]]
