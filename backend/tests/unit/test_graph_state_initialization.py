from app.core.graph.graph_state import build_initial_graph_state


def test_build_initial_graph_state_includes_required_union_fields() -> None:
    state = build_initial_graph_state(
        "Analyze AAPL", [{"role": "user", "content": "Analyze AAPL"}]
    )

    assert state["user_query"] == "Analyze AAPL"
    assert isinstance(state["conversation_history"], list)
    assert state["status"] == "initializing"
    assert state["verification_feedback"] == ""
    assert state["failed_node"] is None
    assert state["current_step"] is None
    assert state["selected_agents"] == []
    assert state["data_check"] == {}
    assert state["replanned_tasks"] == []
    assert state["validation_passed"] is False
    assert state["timeouts"] == {"task_timeout_s": 10.0, "stage_timeout_s": 20.0}

def test_build_initial_graph_state_includes_interactive_planning_fields() -> None:
    state = build_initial_graph_state("Analyze AAPL")

    assert state["plan_status"] is None
    assert state["timeframe"] is None
    assert state["approved_agents"] == []

