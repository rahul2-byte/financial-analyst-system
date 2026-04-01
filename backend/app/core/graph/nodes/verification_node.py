"""Stateless verification node - verifies numeric accuracy of draft report."""

import re
import logging
from typing import Dict, Any, List, Optional

from app.core.node_resources import NodeResources
from app.core.contracts.tool_result import ToolResult

from app.core.orchestration_schemas import ConflictRecord

logger = logging.getLogger(__name__)


def detect_conflicts(agent_outputs: Dict[str, Any]) -> Optional[ConflictRecord]:
    """Detects sentiment contradictions between agents."""
    fundamental = agent_outputs.get("fundamental_analysis", {})
    technical = agent_outputs.get("technical_analysis", {})

    if not fundamental or not technical:
        return None

    # Check for sentiment mismatch (this is simplified for implementation)
    # In a real system, we'd use LLM to detect subtle contradictions
    f_content = str(fundamental).lower()
    t_content = str(technical).lower()

    f_bullish = "bullish" in f_content or "buy" in f_content
    f_bearish = "bearish" in f_content or "sell" in f_content
    t_bullish = "bullish" in t_content or "buy" in t_content
    t_bearish = "bearish" in t_content or "sell" in t_content

    if (f_bullish and t_bearish) or (f_bearish and t_bullish):
        return ConflictRecord(
            contending_agents=["fundamental_analysis", "technical_analysis"],
            agent_outputs={
                "fundamental_analysis": fundamental,
                "technical_analysis": technical,
            },
        )
    return None


class NumericVerifier:
    """Deterministic numeric verification logic."""

    NUMBER_REGEX = re.compile(r"-?[\$₹]?\d+(?:,\d+)*(?:\.\d+)?(?:%|Cr|L|x)?\b")

    @staticmethod
    def normalize_number(val_str: str) -> Optional[float]:
        clean = (
            val_str.replace("$", "")
            .replace("₹", "")
            .replace("%", "")
            .replace(",", "")
            .replace("x", "")
        )

        multiplier = 1.0
        if clean.endswith("Cr"):
            multiplier = 10_000_000.0
            clean = clean[:-2]
        elif clean.endswith("L"):
            multiplier = 100_000.0
            clean = clean[:-1]

        try:
            return float(clean) * multiplier
        except ValueError:
            return None

    @classmethod
    def verify(
        cls, draft_report: str, tool_registry: List[ToolResult]
    ) -> Dict[str, Any]:
        valid_source_values: Dict[str, float] = {}
        for result in tool_registry:
            for key, val in result.extracted_metrics.items():
                if isinstance(val, (int, float)):
                    valid_source_values[key] = float(val)

        if not valid_source_values:
            return {
                "is_valid": True,
                "feedback": "No source data available - skipping verification.",
            }

        found_numbers = cls.NUMBER_REGEX.findall(draft_report)

        mismatches = []
        for num_str in found_numbers:
            normalized = cls.normalize_number(num_str)
            if normalized is not None:
                if not any(
                    abs(normalized - v) < 0.01 * max(abs(v), 1)
                    for v in valid_source_values.values()
                ):
                    mismatches.append(num_str)

        if mismatches:
            return {
                "is_valid": False,
                "feedback": f"Verification FAILED: The following numbers in the report don't match source data: {mismatches}. Please use ONLY numbers from the provided agent outputs.",
            }

        return {
            "is_valid": True,
            "feedback": "All numeric values verified successfully.",
        }


async def verification_node(
    state: Dict[str, Any], resources: NodeResources
) -> Dict[str, Any]:
    """Stateless verification node."""
    draft_report = state.get("draft_report", "")
    tool_registry_raw = state.get("tool_registry", [])

    tool_registry = [
        ToolResult(**t) if isinstance(t, dict) else t for t in tool_registry_raw
    ]

    logger.info("Verification node checking numeric accuracy")

    try:
        # 1. Numeric Verification
        numeric_result = NumericVerifier.verify(draft_report, tool_registry)

        if not numeric_result["is_valid"]:
            current_retry = state.get("verification_retry_count", 0)
            return {
                "verification_passed": False,
                "verification_retry_count": current_retry + 1,
                "verification_feedback": numeric_result["feedback"],
            }

        # 2. Conflict Detection
        agent_outputs = state.get("agent_outputs", {})
        conflict = detect_conflicts(agent_outputs)
        
        iteration = state.get("conflict_iteration_count", 0)
        
        if conflict and iteration == 0:
            logger.warning("Conflict detected between agents, triggering re-run.")
            return {
                "verification_passed": False,
                "conflict_record": conflict.model_dump(),
                "conflict_iteration_count": iteration + 1,
                "verification_feedback": "Fundamental and Technical agents disagree. Re-evaluating for consistency.",
            }
        
        if conflict:
            conflict.is_resolved = True # Mark as resolved (final decision reached after re-run)
            return {
                "verification_passed": True,
                "conflict_record": conflict.model_dump()
            }

        return {"verification_passed": True}

    except Exception as e:
        logger.error(f"Verification node error: {e}", exc_info=True)
        return {
            "verification_passed": False,
            "errors": [f"Verification error: {str(e)}"],
        }
