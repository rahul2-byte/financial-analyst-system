"""Stateless verification node - verifies numeric accuracy of draft report."""
import re
import logging
from typing import Dict, Any, List, Optional

from common.state import ToolResult

logger = logging.getLogger(__name__)


class NumericVerifier:
    """Deterministic numeric verification logic."""
    
    NUMBER_REGEX = re.compile(r"-?[\$₹]?\d+(?:,\d+)*(?:\.\d+)?(?:%|Cr|L|x)?\b")
    WHITELIST_RATIOS = {0.0, 23.6, 38.2, 50.0, 61.8, 78.6, 100.0}
    
    @staticmethod
    def normalize_number(val_str: str) -> Optional[float]:
        clean = (
            val_str.replace("$", "").replace("₹", "").replace("%", "")
            .replace(",", "").replace("x", "")
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
    def verify(cls, draft_report: str, tool_registry: List[ToolResult]) -> Dict[str, Any]:
        valid_source_values = set()
        for result in tool_registry:
            for val in result.extracted_metrics.values():
                if isinstance(val, (int, float)):
                    valid_source_values.add(float(val))
        
        found_numbers = cls.NUMBER_REGEX.findall(draft_report)
        hallucinations = set()
        
        for num_str in found_numbers:
            val = cls.normalize_number(num_str)
            if val is None:
                continue
            
            if num_str.isdigit() and len(num_str) == 4 and num_str.startswith(("19", "20")):
                if val not in valid_source_values:
                    continue
            
            if "%" in num_str and val in cls.WHITELIST_RATIOS:
                continue
            
            is_verified = any(abs(val - sv) < 0.001 for sv in valid_source_values)
            if not is_verified:
                hallucinations.add(num_str)
        
        if not hallucinations:
            return {"is_valid": True, "feedback": "All numeric values verified."}
        
        return {
            "is_valid": False,
            "feedback": f"Numeric errors: {', '.join(hallucinations)}",
        }


async def verification_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Stateless verification node."""
    draft_report = state.get("draft_report", "")
    tool_registry_raw = state.get("tool_registry", [])
    
    tool_registry = [
        ToolResult(**t) if isinstance(t, dict) else t 
        for t in tool_registry_raw
    ]
    
    logger.info("Verification node checking numeric accuracy")
    
    try:
        result = NumericVerifier.verify(draft_report, tool_registry)
        
        if result["is_valid"]:
            return {"verification_passed": True}
        
        current_retry = state.get("verification_retry_count", 0)
        return {
            "verification_passed": False,
            "verification_retry_count": current_retry + 1,
            "verification_feedback": result["feedback"],
            "errors": [result["feedback"]],
        }
        
    except Exception as e:
        logger.error(f"Verification node error: {e}", exc_info=True)
        return {
            "verification_passed": False,
            "errors": [f"Verification error: {str(e)}"],
        }
