"""Canonical ToolResult contract for active orchestration runtime."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    tool_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    input_parameters: dict[str, Any] = Field(default_factory=dict)
    output_data: Any
    extracted_metrics: dict[str, float] = Field(default_factory=dict)

    def auto_extract_metrics(self, max_depth: int = 10) -> None:
        """Flattens nested JSON into extracted_metrics for numeric cross-checking."""
        metrics: dict[str, float] = {}

        def _walk(obj: Any, prefix: str = "", current_depth: int = 0) -> None:
            if current_depth > max_depth:
                return
            if isinstance(obj, dict):
                for key, value in obj.items():
                    _walk(value, f"{prefix}{key}.".lstrip("."), current_depth + 1)
            elif isinstance(obj, list):
                for index, item in enumerate(obj):
                    _walk(item, f"{prefix}{index}.".lstrip("."), current_depth + 1)
            elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
                metrics[prefix.rstrip(".")] = float(obj)
            elif isinstance(obj, str):
                import re

                clean_str = (
                    obj.replace(",", "")
                    .replace("$", "")
                    .replace("₹", "")
                    .replace("%", "")
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
                    value = float(clean_str) * multiplier
                    metrics[prefix.rstrip(".")] = value
                except ValueError:
                    found_numbers = re.findall(
                        r"-?[\$₹]?\d+(?:,\d+)*(?:\.\d+)?(?:%|Cr|L|x)?\b", obj
                    )
                    for index, num_str in enumerate(found_numbers):
                        clean_num = (
                            num_str.replace(",", "")
                            .replace("$", "")
                            .replace("₹", "")
                            .replace("%", "")
                            .replace("x", "")
                        )
                        num_multiplier = 1.0
                        if clean_num.endswith("Cr"):
                            num_multiplier = 10_000_000.0
                            clean_num = clean_num[:-2]
                        elif clean_num.endswith("L"):
                            num_multiplier = 100_000.0
                            clean_num = clean_num[:-1]

                        try:
                            value = float(clean_num) * num_multiplier
                            metrics[f"{prefix.rstrip('.')}_{index}"] = value
                        except ValueError:
                            continue

        import json

        data_to_walk = self.output_data
        if isinstance(self.output_data, str):
            try:
                data_to_walk = json.loads(self.output_data)
            except json.JSONDecodeError:
                pass

        if isinstance(data_to_walk, (dict, list)):
            _walk(data_to_walk)
        elif isinstance(data_to_walk, str):
            _walk([data_to_walk])

        self.extracted_metrics = metrics
