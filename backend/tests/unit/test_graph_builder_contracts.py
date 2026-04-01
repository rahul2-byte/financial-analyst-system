from app.core.graph import graph_builder


class _RecordingGraph:
    def __init__(self):
        self.conditional_edges = {}
        self.entry_point = None

    def add_node(self, *args, **kwargs):
        return None

    def add_edge(self, *args, **kwargs):
        return None

    def add_conditional_edges(self, node_name, route_fn, mapping):
        self.conditional_edges[node_name] = mapping

    def set_entry_point(self, entry_point):
        self.entry_point = entry_point

    def compile(self):
        return self


def test_build_graph_conditional_edges_match_route_contracts(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.entry_point == "router_node"
    assert set(recorder.conditional_edges["router_node"].keys()) == {
        "run_goal_hypothesis",
        "run_data_check",
        "run_data_plan",
        "run_data_fetch",
        "run_research_plan",
        "run_research_exec",
        "run_synthesis",
        "run_critic",
        "run_reflection",
        "run_conflict_resolution",
        "run_validation",
        "terminate_success",
        "terminate_insufficient_data",
        "terminate_budget_exceeded",
        "terminate_failure",
    }
    assert set(recorder.conditional_edges["synthesis_node"].keys()) == {"run_critic"}
    assert set(recorder.conditional_edges["conflict_resolution_node"].keys()) == {
        "run_synthesis"
    }
    assert set(recorder.conditional_edges["validation_node"].keys()) == {
        "run_router",
    }
    assert set(recorder.conditional_edges["goal_hypothesis_node"].keys()) == {
        "run_router",
    }
    assert set(recorder.conditional_edges["data_fetch_node"].keys()) == {
        "run_router",
    }
    assert set(recorder.conditional_edges["data_checker_node"].keys()) == {
        "run_data_plan",
        "run_router",
    }
    assert set(recorder.conditional_edges["research_execution_node"].keys()) == {
        "run_router",
    }
    assert set(recorder.conditional_edges["critic_node"].keys()) == {
        "run_router",
    }
    assert set(recorder.conditional_edges["reflection_node"].keys()) == {
        "run_router",
    }
    assert set(recorder.conditional_edges["research_planner_node"].keys()) == {
        "run_router",
    }
    assert set(recorder.conditional_edges["data_planner_node"].keys()) == {
        "run_router",
    }
    assert "__end__" in recorder.conditional_edges["router_node"].values()


def test_router_has_terminal_paths(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    terminal_routes = {
        "terminate_success",
        "terminate_insufficient_data",
        "terminate_budget_exceeded",
        "terminate_failure",
    }
    assert terminal_routes.issubset(set(recorder.conditional_edges["router_node"].keys()))
    assert "__end__" in set(recorder.conditional_edges["router_node"].values())


def test_conflict_flow_contract(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["conflict_resolution_node"]["run_synthesis"] == "synthesis_node"
    assert recorder.conditional_edges["synthesis_node"]["run_critic"] == "critic_node"


def test_router_driven_nodes_return_to_router(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    return_to_router_nodes = [
        "goal_hypothesis_node",
        "data_planner_node",
        "data_fetch_node",
        "research_planner_node",
        "research_execution_node",
        "critic_node",
        "reflection_node",
        "validation_node",
    ]
    for node in return_to_router_nodes:
        assert recorder.conditional_edges[node] == {"run_router": "router_node"}


def test_data_checker_can_short_circuit_to_router(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["data_checker_node"]["run_router"] == "router_node"
    assert recorder.conditional_edges["data_checker_node"]["run_data_plan"] == "data_planner_node"


def test_router_maps_research_execution(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["router_node"]["run_research_exec"] == "research_execution_node"


def test_router_maps_validation(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["router_node"]["run_validation"] == "validation_node"


def test_router_maps_data_check(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["router_node"]["run_data_check"] == "data_checker_node"


def test_router_maps_goal_hypothesis(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["router_node"]["run_goal_hypothesis"] == "goal_hypothesis_node"


def test_router_maps_conflict_resolution(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["router_node"]["run_conflict_resolution"] == "conflict_resolution_node"


def test_router_maps_reflection(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["router_node"]["run_reflection"] == "reflection_node"


def test_router_maps_synthesis(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["router_node"]["run_synthesis"] == "synthesis_node"


def test_router_maps_critic(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["router_node"]["run_critic"] == "critic_node"


def test_router_maps_data_plan(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["router_node"]["run_data_plan"] == "data_planner_node"


def test_router_maps_data_fetch(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["router_node"]["run_data_fetch"] == "data_fetch_node"


def test_router_maps_research_plan(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["router_node"]["run_research_plan"] == "research_planner_node"


def test_router_end_mappings(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["router_node"]["terminate_success"] == "__end__"
    assert recorder.conditional_edges["router_node"]["terminate_insufficient_data"] == "__end__"
    assert recorder.conditional_edges["router_node"]["terminate_budget_exceeded"] == "__end__"
    assert recorder.conditional_edges["router_node"]["terminate_failure"] == "__end__"


def test_router_to_router_loop_exists(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    for node in [
        "goal_hypothesis_node",
        "data_planner_node",
        "data_fetch_node",
        "research_planner_node",
        "research_execution_node",
        "critic_node",
        "reflection_node",
        "validation_node",
    ]:
        assert recorder.conditional_edges[node]["run_router"] == "router_node"


def test_synthesis_forces_critic_after_conflict_resolution(monkeypatch):
    recorder = _RecordingGraph()

    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)

    graph_builder.build_graph()

    assert recorder.conditional_edges["conflict_resolution_node"]["run_synthesis"] == "synthesis_node"
    assert recorder.conditional_edges["synthesis_node"]["run_critic"] == "critic_node"


def test_data_checker_branching_contract(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()

    assert set(recorder.conditional_edges["data_checker_node"].keys()) == {
        "run_data_plan",
        "run_router",
    }


def test_entrypoint_is_router(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()

    assert recorder.entry_point == "router_node"


def test_validation_returns_router(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert recorder.conditional_edges["validation_node"] == {"run_router": "router_node"}


def test_reflection_returns_router(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert recorder.conditional_edges["reflection_node"] == {"run_router": "router_node"}


def test_critic_returns_router(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert recorder.conditional_edges["critic_node"] == {"run_router": "router_node"}


def test_research_exec_returns_router(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert recorder.conditional_edges["research_execution_node"] == {"run_router": "router_node"}


def test_research_planner_returns_router(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert recorder.conditional_edges["research_planner_node"] == {"run_router": "router_node"}


def test_data_planner_returns_router(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert recorder.conditional_edges["data_planner_node"] == {"run_router": "router_node"}


def test_data_fetch_returns_router(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert recorder.conditional_edges["data_fetch_node"] == {"run_router": "router_node"}


def test_goal_returns_router(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert recorder.conditional_edges["goal_hypothesis_node"] == {"run_router": "router_node"}


def test_router_has_all_expected_nodes(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()

    expected_nodes = {
        "router_node",
        "goal_hypothesis_node",
        "data_checker_node",
        "data_planner_node",
        "data_fetch_node",
        "research_planner_node",
        "research_execution_node",
        "synthesis_node",
        "critic_node",
        "reflection_node",
        "conflict_resolution_node",
        "validation_node",
    }
    # Node recording not available in this recorder, so assert edge origins include all key nodes.
    assert expected_nodes.issubset(set(recorder.conditional_edges.keys()) | {"router_node"})


def test_router_terminal_values_map_to_end(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    values = recorder.conditional_edges["router_node"]
    for key in [
        "terminate_success",
        "terminate_insufficient_data",
        "terminate_budget_exceeded",
        "terminate_failure",
    ]:
        assert values[key] == "__end__"


def test_data_checker_has_router_escape(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert "run_router" in recorder.conditional_edges["data_checker_node"]


def test_conflict_node_no_direct_validation(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert "run_validation" not in recorder.conditional_edges["conflict_resolution_node"]


def test_synthesis_only_routes_to_critic(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert recorder.conditional_edges["synthesis_node"] == {"run_critic": "critic_node"}


def test_router_has_goal_route(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert recorder.conditional_edges["router_node"]["run_goal_hypothesis"] == "goal_hypothesis_node"


def test_router_has_data_routes(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert recorder.conditional_edges["router_node"]["run_data_check"] == "data_checker_node"
    assert recorder.conditional_edges["router_node"]["run_data_plan"] == "data_planner_node"
    assert recorder.conditional_edges["router_node"]["run_data_fetch"] == "data_fetch_node"


def test_router_has_research_routes(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert recorder.conditional_edges["router_node"]["run_research_plan"] == "research_planner_node"
    assert recorder.conditional_edges["router_node"]["run_research_exec"] == "research_execution_node"


def test_router_has_quality_routes(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    assert recorder.conditional_edges["router_node"]["run_synthesis"] == "synthesis_node"
    assert recorder.conditional_edges["router_node"]["run_critic"] == "critic_node"
    assert recorder.conditional_edges["router_node"]["run_reflection"] == "reflection_node"
    assert recorder.conditional_edges["router_node"]["run_conflict_resolution"] == "conflict_resolution_node"
    assert recorder.conditional_edges["router_node"]["run_validation"] == "validation_node"


def test_router_terminal_set(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _: recorder)
    graph_builder.build_graph()
    keys = set(recorder.conditional_edges["router_node"].keys())
    assert {"terminate_success", "terminate_insufficient_data", "terminate_budget_exceeded", "terminate_failure"}.issubset(keys)
