from typing import TypedDict, Dict, Any, List, Optional, Annotated
import operator


def merge_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """Custom merge function for dicts - right dict takes precedence."""
    return {**left, **right}


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
