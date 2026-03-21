import re
import logging
from typing import List, Optional
from common.state import ToolResult
from common.schemas import VerificationResponse

logger = logging.getLogger(__name__)


class VerificationAgent:
    """
    Deterministic agent that cross-checks all numbers in a draft report
    against the extracted metrics from the tool registry.
    """

    def __init__(self):
        # Regex to find numbers, currency, and percentages (supporting negatives and Indian suffixes)
        # E.g., $1,234.56, ₹500 Cr, -45%, -1000, 1.2
        self.number_regex = re.compile(r"-?[\$₹]?\d+(?:,\d+)*(?:\.\d+)?(?:%|Cr|L|x)?\b")

    def _normalize_number(self, val_str: str) -> Optional[float]:
        """Removes symbols and commas, converts to float. Handles ₹, L, Cr, x."""
        clean_str = (
            val_str.replace("$", "")
            .replace("₹", "")
            .replace("%", "")
            .replace(",", "")
            .replace("x", "")
        )

        multiplier = 1.0
        if clean_str.endswith("Cr"):
            multiplier = 10_000_000.0
            clean_str = clean_str[:-2]
        elif clean_str.endswith("L"):
            multiplier = 100_000.0
            clean_str = clean_str[:-1]

        try:
            return float(clean_str) * multiplier
        except ValueError:
            return None

    def verify(
        self, user_query: str, draft_report: str, tool_registry: List[ToolResult]
    ) -> VerificationResponse:
        """
        Extracts all numbers from the draft report and verifies them against the tool registry.
        """
        try:
            # 1. Flatten all metrics from tool_registry into a single lookup set
            valid_source_values = set()
            for result in tool_registry:
                for val in result.extracted_metrics.values():
                    valid_source_values.add(float(val))

            # 2. Extract numbers from the draft report
            found_numbers = self.number_regex.findall(draft_report)

            hallucinations = set()

            # Whitelist for mathematical constants and common ratios
            WHITELIST_RATIOS = {0.0, 23.6, 38.2, 50.0, 61.8, 78.6, 100.0}

            for num_str in found_numbers:
                val = self._normalize_number(num_str)
                if val is None:
                    continue

                # Clean numeric value for ratio check
                is_percentage = "%" in num_str

                # Filter out likely non-metric numbers to reduce false positives:
                # - 4-digit integers starting with 19 or 20 (years)
                # - Small integers (0-10) commonly used in lists or counting
                is_likely_year = (
                    num_str.isdigit()
                    and len(num_str) == 4
                    and num_str.startswith(("19", "20"))
                )
                is_small_int = num_str.isdigit() and 0 <= int(num_str) <= 10

                if is_likely_year or is_small_int:
                    # Only flag if it's NOT in our valid sources
                    if val not in valid_source_values:
                        continue

                # Special Check: Is it a common Fibonacci ratio or mathematical constant?
                if is_percentage and val in WHITELIST_RATIOS:
                    continue

                # Simple check: Is this numeric value present in ANY of our tool results?
                # We use a small tolerance for floating point comparisons
                is_verified = False
                for source_val in valid_source_values:
                    # Check for exact match or within tolerance
                    if abs(val - source_val) < 0.001:
                        is_verified = True
                        break

                if not is_verified:
                    hallucinations.add(num_str)

            if not hallucinations:
                return VerificationResponse(
                    status="success",
                    is_valid=True,
                    feedback="All numeric values in the report were verified against source data.",
                )
            else:
                hallucination_list = ", ".join(list(hallucinations))
                feedback = (
                    f"Numeric Consistency Error: The following values could not be verified: {hallucination_list}. "
                    "You must only use numbers found in the tool results. "
                    "Do not estimate, hallucinate, or use external knowledge for numeric data."
                )
                return VerificationResponse(
                    status="success", is_valid=False, feedback=feedback
                )
        except Exception as e:
            logger.error(f"VerificationAgent error: {e}", exc_info=True)
            return VerificationResponse(
                status="failure",
                is_valid=False,
                feedback=f"Verification system error: {str(e)}",
            )
