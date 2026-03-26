from typing import TypedDict, Dict, Any, List, Optional


def merge_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """Custom merge function for dicts - right dict takes precedence."""
    return {**left, **right}


class ResearchGraphState(TypedDict):
    user_query: str
    conversation_history: List[Dict[str, str]]
    plan: Optional[Dict[str, Any]]
    executed_steps: List[Dict[str, Any]]
    agent_outputs: Dict[str, Any]
    tool_registry: List[Dict[str, Any]]
    draft_report: Optional[str]
    final_report: Optional[str]
    synthesis_retry_count: int
    verification_retry_count: int
    errors: List[str]
