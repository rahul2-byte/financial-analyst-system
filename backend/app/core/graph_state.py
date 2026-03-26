from typing import TypedDict, Dict, Any, List, Optional
from operator import add
from functools import reduce


def merge_dicts(left: Dict[Any, Any], right: Dict[Any, Any]) -> Dict[Any, Any]:
    """Custom merge function for dicts - right dict takes precedence."""
    merged = left.copy()
    merged.update(right)
    return merged


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
    errors: List[str]
