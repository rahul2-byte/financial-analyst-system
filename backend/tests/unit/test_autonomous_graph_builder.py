from app.core import graph_builder


class _RecordingGraph:
    def __init__(self):
        self.conditional_edges = {}
        self.nodes = {}
        self.entry_point = None

    def add_node(self, name, func):
        self.nodes[name] = func

    def add_edge(self, *_args, **_kwargs):
        return None

    def add_conditional_edges(self, node_name, _route_fn, mapping):
        self.conditional_edges[node_name] = mapping

    def set_entry_point(self, name):
        self.entry_point = name

    def compile(self):
        return self


def test_graph_builder_uses_router_as_entrypoint(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _state: recorder)

    graph_builder.build_graph()

    assert recorder.entry_point == "router_node"


def test_router_conditional_edges_cover_autonomous_decisions(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _state: recorder)

    graph_builder.build_graph()

    expected = {
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
        "__end__",
    }
    assert expected.issubset(set(recorder.conditional_edges["router_node"].values()))


def test_conflict_flow_is_explicit(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(graph_builder, "StateGraph", lambda _state: recorder)

    graph_builder.build_graph()

    conflict_edges = recorder.conditional_edges["conflict_resolution_node"]
    synthesis_edges = recorder.conditional_edges["synthesis_node"]

    assert conflict_edges["run_synthesis"] == "synthesis_node"
    assert synthesis_edges["run_critic"] == "critic_node"
