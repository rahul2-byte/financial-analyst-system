from app.core.graph.node_helpers import build_node_error, build_node_success


def test_build_node_success_creates_standard_tool_registry_payload():
    result = build_node_success(
        agent_output_key="retrieval",
        agent_output={"results": [{"score": 0.91}]},
        tool_name="retrieval:hybrid_search",
        input_parameters={"query": "AAPL"},
        tool_output={"results": [{"score": 0.91}]},
    )

    assert "agent_outputs" in result
    assert "tool_registry" in result
    assert result["agent_outputs"]["retrieval"]["results"][0]["score"] == 0.91
    assert result["tool_registry"][0]["tool_name"] == "retrieval:hybrid_search"
    assert result["tool_registry"][0]["extracted_metrics"]["results.0.score"] == 0.91


def test_build_node_error_supports_prefix():
    result = build_node_error(ValueError("boom"), prefix="Web search failed: ")
    assert result == {"errors": ["Web search failed: boom"]}
