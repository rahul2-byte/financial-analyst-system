import pytest
from unittest.mock import AsyncMock

from app.core.tool_registry import ToolRegistry, ToolDefinition
from app.core.graph_state import ResearchGraphState
from app.core.tool_executor import ToolExecutorNode, execute_tool_node


@pytest.fixture
def clean_registry():
    """Provide a clean ToolRegistry for each test."""
    registry = ToolRegistry()
    registry.clear()
    yield registry
    registry.clear()


@pytest.fixture
def mock_handler():
    """Create a mock handler that returns a predefined result."""
    handler = AsyncMock(return_value={"result": "success", "data": 42})
    return handler


class TestToolExecutorNode:
    """Tests for ToolExecutorNode class."""

    def test_initialization(self, clean_registry):
        """Test that ToolExecutorNode initializes correctly."""
        node = ToolExecutorNode()
        assert node.registry is not None

    @pytest.mark.asyncio
    async def test_executes_registered_tool(self, clean_registry, mock_handler):
        """Test that node executes a registered tool handler."""
        clean_registry.register("test_ns", ToolDefinition(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object", "properties": {}},
            handler=mock_handler,
        ))

        state: ResearchGraphState = {
            "user_query": "test query",
            "conversation_history": [],
            "plan": None,
            "executed_steps": [],
            "agent_outputs": {},
            "tool_registry": [],
            "draft_report": None,
            "final_report": None,
            "synthesis_retry_count": 0,
            "verification_retry_count": 0,
            "verification_feedback": None,
            "errors": [],
            "current_tool": "test_ns:test_tool",
            "tool_args": {"param1": "value1"},
        }

        node = ToolExecutorNode()
        result = await node.execute(state)

        mock_handler.assert_called_once_with(**state["tool_args"])
        assert "tool_result" in result
        assert result["tool_result"]["result"] == "success"

    @pytest.mark.asyncio
    async def test_tool_not_found_error(self, clean_registry):
        """Test that node raises error when tool not found."""
        state: ResearchGraphState = {
            "user_query": "test query",
            "conversation_history": [],
            "plan": None,
            "executed_steps": [],
            "agent_outputs": {},
            "tool_registry": [],
            "draft_report": None,
            "final_report": None,
            "synthesis_retry_count": 0,
            "verification_retry_count": 0,
            "verification_feedback": None,
            "errors": [],
            "current_tool": "nonexistent:tool",
            "tool_args": {},
        }

        node = ToolExecutorNode()
        result = await node.execute(state)

        assert "errors" in result
        assert any("not found" in err.lower() for err in result["errors"])

    @pytest.mark.asyncio
    async def test_handler_execution_error(self, clean_registry):
        """Test that node handles handler execution errors."""
        async def failing_handler(**kwargs):
            raise ValueError("Handler failed")

        clean_registry.register("test_ns", ToolDefinition(
            name="failing_tool",
            description="Failing tool",
            parameters={"type": "object", "properties": {}},
            handler=failing_handler,
        ))

        state: ResearchGraphState = {
            "user_query": "test query",
            "conversation_history": [],
            "plan": None,
            "executed_steps": [],
            "agent_outputs": {},
            "tool_registry": [],
            "draft_report": None,
            "final_report": None,
            "synthesis_retry_count": 0,
            "verification_retry_count": 0,
            "verification_feedback": None,
            "errors": [],
            "current_tool": "test_ns:failing_tool",
            "tool_args": {},
        }

        node = ToolExecutorNode()
        result = await node.execute(state)

        assert "errors" in result
        assert any("handler" in err.lower() for err in result["errors"])

    @pytest.mark.asyncio
    async def test_missing_current_tool(self, clean_registry):
        """Test that node handles missing current_tool in state."""
        state: ResearchGraphState = {
            "user_query": "test query",
            "conversation_history": [],
            "plan": None,
            "executed_steps": [],
            "agent_outputs": {},
            "tool_registry": [],
            "draft_report": None,
            "final_report": None,
            "synthesis_retry_count": 0,
            "verification_retry_count": 0,
            "verification_feedback": None,
            "errors": [],
        }

        node = ToolExecutorNode()
        result = await node.execute(state)

        assert "errors" in result
        assert any("current_tool" in err.lower() for err in result["errors"])


class TestExecuteToolNode:
    """Tests for the LangGraph node function."""

    @pytest.mark.asyncio
    async def test_node_returns_dict(self, clean_registry, mock_handler):
        """Test that execute_tool_node returns a valid state dict."""
        clean_registry.register("test_ns", ToolDefinition(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object", "properties": {}},
            handler=mock_handler,
        ))

        state: ResearchGraphState = {
            "user_query": "test query",
            "conversation_history": [],
            "plan": None,
            "executed_steps": [],
            "agent_outputs": {},
            "tool_registry": [],
            "draft_report": None,
            "final_report": None,
            "synthesis_retry_count": 0,
            "verification_retry_count": 0,
            "verification_feedback": None,
            "errors": [],
            "current_tool": "test_ns:test_tool",
            "tool_args": {},
        }

        result = await execute_tool_node(state)

        assert isinstance(result, dict)
        assert "tool_result" in result

    @pytest.mark.asyncio
    async def test_node_updates_state_correctly(self, clean_registry, mock_handler):
        """Test that node updates state with tool result."""
        clean_registry.register("test_ns", ToolDefinition(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object", "properties": {}},
            handler=mock_handler,
        ))

        state: ResearchGraphState = {
            "user_query": "test query",
            "conversation_history": [],
            "plan": None,
            "executed_steps": [],
            "agent_outputs": {},
            "tool_registry": [],
            "draft_report": None,
            "final_report": None,
            "synthesis_retry_count": 0,
            "verification_retry_count": 0,
            "verification_feedback": None,
            "errors": [],
            "current_tool": "test_ns:test_tool",
            "tool_args": {"key": "value"},
        }

        result = await execute_tool_node(state)

        mock_handler.assert_called_once_with(key="value")
        assert result["tool_result"]["data"] == 42
