from __future__ import annotations

import json

from app.core.logging import SessionLogger


def test_session_logger_writes_jsonl_for_step_trace_and_error() -> None:
    logger = SessionLogger("test query", trace_id="abc123abc123abcd")

    logger.log_step(
        "custom_step", "step explanation", parameters={"k": "v"}, data={"x": 1}
    )
    logger.log_trace("node_start", {"node": "router_node", "node_call_index": 1})
    logger.log_error("custom_error", "error happened", data={"reason": "x"})

    assert logger.jsonl_file.exists()

    lines = logger.jsonl_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 3

    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["seq"] == 1
    assert parsed[1]["seq"] == 2
    assert parsed[2]["seq"] == 3
    assert all(entry["trace_id"] == "abc123abc123abcd" for entry in parsed[:3])
    assert parsed[1]["event_name"] == "STEP_TRACE_NODE_START"
