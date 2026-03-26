from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


class ToolResult(BaseModel):
    tool_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    input_parameters: Dict[str, Any] = Field(default_factory=dict)
    output_data: Any  # The raw JSON/Dict from the tool
    extracted_metrics: Dict[str, float] = Field(default_factory=dict)  # For fast lookup

    def auto_extract_metrics(self, max_depth: int = 10) -> None:
        """Flattens nested JSON into extracted_metrics for numeric cross-checking."""
        metrics = {}

        def _walk(obj: Any, prefix: str = "", current_depth: int = 0) -> None:
            if current_depth > max_depth:
                return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    _walk(v, f"{prefix}{k}.".lstrip("."), current_depth + 1)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    _walk(item, f"{prefix}{i}.".lstrip("."), current_depth + 1)
            elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
                metrics[prefix.rstrip(".")] = float(obj)
            elif isinstance(obj, str):
                # Attempt to extract numbers from strings, ignoring common formatting characters
                import re

                clean_str = (
                    obj.replace(",", "")
                    .replace("$", "")
                    .replace("₹", "")
                    .replace("%", "")
                )

                multiplier = 1.0
                if clean_str.endswith("Cr"):
                    multiplier = 10_000_000.0
                    clean_str = clean_str[:-2]
                elif clean_str.endswith("L"):
                    multiplier = 100_000.0
                    clean_str = clean_str[:-1]

                try:
                    val = float(clean_str) * multiplier
                    metrics[prefix.rstrip(".")] = val
                except ValueError:
                    # If it's a longer string with multiple numbers, extract them all using a regex
                    found_numbers = re.findall(
                        r"-?[\$₹]?\d+(?:,\d+)*(?:\.\d+)?(?:%|Cr|L)?\b", obj
                    )
                    for i, num_str in enumerate(found_numbers):
                        clean_num = (
                            num_str.replace(",", "")
                            .replace("$", "")
                            .replace("₹", "")
                            .replace("%", "")
                        )
                        m = 1.0
                        if clean_num.endswith("Cr"):
                            m = 10_000_000.0
                            clean_num = clean_num[:-2]
                        elif clean_num.endswith("L"):
                            m = 100_000.0
                            clean_num = clean_num[:-1]

                        try:
                            val = float(clean_num) * m
                            metrics[f"{prefix.rstrip('.')}_{i}"] = val
                        except ValueError:
                            pass

        # Ensure output_data is processed even if it's a JSON string
        import json

        data_to_walk = self.output_data
        if isinstance(self.output_data, str):
            try:
                data_to_walk = json.loads(self.output_data)
            except json.JSONDecodeError:
                pass  # Will be handled by the _walk root check if it's not a dict/list

        if isinstance(data_to_walk, (dict, list)):
            _walk(data_to_walk)
        elif isinstance(data_to_walk, str):
            _walk([data_to_walk])  # wrap string in list to extract numbers from it

        self.extracted_metrics = metrics


class TaskMetadata(BaseModel):
    agent: str
    status: str
    attempts: int = 0
    validation_history: List[Dict[str, Any]] = Field(default_factory=list)
    failure_reason: Optional[str] = None


class ResearchState(BaseModel):
    query: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tool_registry: List[ToolResult] = Field(default_factory=list)
    agent_outputs: Dict[str, Any] = Field(default_factory=dict)
    verification_errors: List[str] = Field(default_factory=list)
    retry_count: int = 0
    global_status: str = "IN_PROGRESS"
    tasks_metadata: Dict[str, TaskMetadata] = Field(default_factory=dict)
