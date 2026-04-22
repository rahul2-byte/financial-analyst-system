from app.core.audit import build_node_audit_entry, summarize_node_output


def test_build_node_audit_entry_extracts_standard_context() -> None:
    state = {
        "goal": {
            "ticker": "HDFCBANK",
            "instruments": [{"trading_symbol": "HDFCBANK"}],
        },
        "timeframe": "1y",
        "iteration_count": 3,
        "router_decision": "run_research_plan",
        "tasks": [{"task_id": "fundamental_analysis", "agent": "fundamental_analysis"}],
    }
    payload = {
        "status": "success",
        "reasoning": "Built tasks.",
        "next_action": "run_research_context",
        "tasks": [{"task_id": f"t{i}"} for i in range(6)],
        "task_contexts": [{"task_id": f"ctx{i}"} for i in range(7)],
        "results": [{"task_id": f"result{i}"} for i in range(8)],
        "data_plan": {f"step{i}": i for i in range(6)},
        "errors": "none",
    }

    entry = build_node_audit_entry("research_plan_node", state, payload)

    assert entry["node"] == "research_plan_node"
    assert entry["ticker"] == "HDFCBANK"
    assert entry["timeframe"] == "1y"
    assert entry["status"] == "success"
    assert entry["next_action"] == "run_research_context"
    assert entry["errors"] == ["none"]
    assert entry["output_summary"]["status"] == "success"
    assert entry["output_summary"]["reasoning"] == "Built tasks."
    assert entry["output_summary"]["next_action"] == "run_research_context"
    assert len(entry["output_summary"]["tasks"]) == 5
    assert entry["output_summary"]["task_count"] == 6
    assert len(entry["output_summary"]["task_contexts"]) == 5
    assert entry["output_summary"]["task_context_count"] == 7
    assert len(entry["output_summary"]["results"]) == 5
    assert entry["output_summary"]["result_count"] == 8
    assert len(entry["output_summary"]["data_plan"]) == 5
    assert entry["output_summary"]["data_plan_count"] == 6


def test_summarize_node_output_truncates_large_lists() -> None:
    output = {
        "status": "success",
        "reasoning": "Built tasks.",
        "next_action": "run_research_context",
        "errors": ["warning"],
        "tasks": [{"task_id": f"t{i}"} for i in range(20)],
        "task_contexts": [{"task_id": f"ctx{i}"} for i in range(9)],
        "results": [{"task_id": f"result{i}"} for i in range(11)],
        "data_plan": {f"step{i}": i for i in range(8)},
    }

    summary = summarize_node_output(output)

    assert summary["status"] == "success"
    assert summary["reasoning"] == "Built tasks."
    assert summary["next_action"] == "run_research_context"
    assert summary["errors"] == ["warning"]
    assert len(summary["tasks"]) == 5
    assert summary["task_count"] == 20
    assert len(summary["task_contexts"]) == 5
    assert summary["task_context_count"] == 9
    assert len(summary["results"]) == 5
    assert summary["result_count"] == 11
    assert len(summary["data_plan"]) == 5
    assert summary["data_plan_count"] == 8
