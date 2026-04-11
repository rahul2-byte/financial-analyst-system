"""Compatibility facade for autonomous quality nodes.

Runtime code should prefer importing from `agents.quality`.
This module is intentionally kept to avoid breaking existing imports and tests.
"""

from agents.quality import (
    conflict_resolution_node,
    critic_node,
    evaluator_node,
    synthesis_node,
)

__all__ = [
    "conflict_resolution_node",
    "critic_node",
    "evaluator_node",
    "synthesis_node",
]
