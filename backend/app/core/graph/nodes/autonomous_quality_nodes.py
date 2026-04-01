"""Compatibility facade for autonomous quality nodes.

Runtime code should prefer importing from `app.core.graph.nodes.autonomous_quality`.
This module is intentionally kept to avoid breaking existing imports and tests.
"""

from app.core.graph.nodes.autonomous_quality import (
    autonomous_conflict_resolution_node,
    autonomous_critic_node,
    autonomous_reflection_node,
    autonomous_synthesis_node,
)

__all__ = [
    "autonomous_conflict_resolution_node",
    "autonomous_critic_node",
    "autonomous_reflection_node",
    "autonomous_synthesis_node",
]
