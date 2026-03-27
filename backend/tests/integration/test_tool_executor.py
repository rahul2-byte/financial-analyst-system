import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.tool_executor import ToolExecutorNode, execute_tool_node
from app.core.tool_registry import ToolRegistry, ToolDefinition


@pytest.fixture
def clean_registry():
    registry = ToolRegistry()
    registry.clear()
    return registry


@pytest.mark.asyncio
async def test_tool_executor_routes_to_handler(clean_registry):
    """Test that executor routes to correct handler."""
    mock_handler = AsyncMock(return_value='{"result": "success"}')
    tool_def = ToolDefinition(
        name="test_tool",
        description="Test",
        parameters={"type": "object"},
        handler=mock_handler,
    )

    clean_registry.register("test", tool_def)

    executor = ToolExecutorNode()
    state = {
        "current_tool": "test:test_tool",
        "tool_args": {"param": "value"},
    }

    result = await executor.execute(state)
    assert mock_handler.called
    assert "tool_results" in result


@pytest.mark.asyncio
async def test_tool_executor_tool_not_found(clean_registry):
    """Test error when tool not found."""
    executor = ToolExecutorNode()
    state = {
        "current_tool": "nonexistent:tool",
        "tool_args": {},
    }

    result = await executor.execute(state)
    assert "errors" in result
    assert "not found" in result["errors"][0]


@pytest.mark.asyncio
async def test_tool_executor_no_tool_specified():
    """Test error when no tool specified."""
    executor = ToolExecutorNode()
    state = {}

    result = await executor.execute(state)
    assert "errors" in result
    assert "No tool specified" in result["errors"][0]


@pytest.mark.asyncio
async def test_tool_executor_no_handler(clean_registry):
    """Test error when tool has no handler."""
    tool_def = ToolDefinition(
        name="no_handler",
        description="Test",
        parameters={"type": "object"},
    )
    clean_registry.register("test", tool_def)

    executor = ToolExecutorNode()
    state = {
        "current_tool": "test:no_handler",
        "tool_args": {},
    }

    result = await executor.execute(state)
    assert "errors" in result
    assert "no handler" in result["errors"][0].lower()


@pytest.mark.asyncio
async def test_execute_tool_node_function(clean_registry):
    """Test the LangGraph node function."""
    mock_handler = AsyncMock(return_value="result")
    tool_def = ToolDefinition(
        name="node_test",
        description="Test",
        parameters={"type": "object"},
        handler=mock_handler,
    )
    clean_registry.register("test", tool_def)

    state = {
        "current_tool": "test:node_test",
        "tool_args": {},
    }

    result = await execute_tool_node(state)
    assert mock_handler.called
