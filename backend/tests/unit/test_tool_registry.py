import pytest
from typing import Any, Dict, Callable
from app.core.tool_registry import ToolRegistry, ToolDefinition


@pytest.fixture
def tool_registry():
    """Fixture that provides a fresh ToolRegistry instance."""
    registry = ToolRegistry()
    registry.clear()
    return registry


def create_mock_handler(name: str) -> Callable:
    """Create a mock async handler function."""
    async def handler(*args, **kwargs):
        return f"result from {name}"
    return handler


def test_tool_definition_model():
    """Test ToolDefinition Pydantic model creation."""
    params: Dict[str, Any] = {"type": "object", "properties": {"query": {"type": "string"}}}
    handler = create_mock_handler("test_tool")

    tool = ToolDefinition(
        name="test_tool",
        description="A test tool",
        parameters=params,
        handler=handler,
    )

    assert tool.name == "test_tool"
    assert tool.description == "A test tool"
    assert tool.parameters == params
    assert tool.handler is not None


def test_tool_definition_optional_handler():
    """Test ToolDefinition can be created without handler."""
    tool = ToolDefinition(
        name="no_handler_tool",
        description="A tool without handler",
        parameters={"type": "object"},
    )

    assert tool.name == "no_handler_tool"
    assert tool.handler is None


def test_singleton_behavior():
    """Test that ToolRegistry is a singleton."""
    registry1 = ToolRegistry()
    registry2 = ToolRegistry()

    assert registry1 is registry2


def test_register_tool(tool_registry):
    """Test tool registration."""
    params: Dict[str, Any] = {"type": "object", "properties": {}}
    handler = create_mock_handler("market_check")

    tool_registry.register("market", ToolDefinition(
        name="check_db_status",
        description="Check database status",
        parameters=params,
        handler=handler,
    ))

    tools = tool_registry.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "check_db_status"


def test_register_multiple_tools_same_namespace(tool_registry):
    """Test registering multiple tools in the same namespace."""
    params: Dict[str, Any] = {"type": "object", "properties": {}}

    tool_registry.register("market", ToolDefinition(
        name="check_db_status",
        description="Check database status",
        parameters=params,
    ))
    tool_registry.register("market", ToolDefinition(
        name="get_table_names",
        description="Get table names",
        parameters=params,
    ))

    tools = tool_registry.list_tools()
    assert len(tools) == 2


def test_register_different_namespaces(tool_registry):
    """Test registering tools in different namespaces."""
    params: Dict[str, Any] = {"type": "object", "properties": {}}

    tool_registry.register("market", ToolDefinition(
        name="check_db_status",
        description="Check database status",
        parameters=params,
    ))
    tool_registry.register("data", ToolDefinition(
        name="fetch_stock_price",
        description="Fetch stock price",
        parameters=params,
    ))
    tool_registry.register("analysis", ToolDefinition(
        name="run_fundamental_scan",
        description="Run fundamental scan",
        parameters=params,
    ))

    tools = tool_registry.list_tools()
    assert len(tools) == 3


def test_get_tool_by_name(tool_registry):
    """Test retrieving a tool by its full name with namespace."""
    params: Dict[str, Any] = {"type": "object", "properties": {}}
    handler = create_mock_handler("check_db")

    tool_registry.register("market", ToolDefinition(
        name="check_db_status",
        description="Check database status",
        parameters=params,
        handler=handler,
    ))

    tool = tool_registry.get_tool("market:check_db_status")
    assert tool is not None
    assert tool.name == "check_db_status"
    assert tool.description == "Check database status"


def test_get_tool_not_found(tool_registry):
    """Test retrieving a non-existent tool returns None."""
    tool = tool_registry.get_tool("nonexistent:tool")
    assert tool is None


def test_list_tools_returns_all_tools(tool_registry):
    """Test list_tools returns all registered tools."""
    params: Dict[str, Any] = {"type": "object", "properties": {}}

    tool_registry.register("market", ToolDefinition(
        name="check_db_status",
        description="Check DB",
        parameters=params,
    ))
    tool_registry.register("data", ToolDefinition(
        name="fetch_stock_price",
        description="Fetch price",
        parameters=params,
    ))

    tools = tool_registry.list_tools()
    assert len(tools) == 2
    names = [t.name for t in tools]
    assert "check_db_status" in names
    assert "fetch_stock_price" in names


def test_clear_removes_all_tools(tool_registry):
    """Test that clear() removes all registered tools."""
    params: Dict[str, Any] = {"type": "object", "properties": {}}

    tool_registry.register("market", ToolDefinition(
        name="check_db_status",
        description="Check DB",
        parameters=params,
    ))

    assert len(tool_registry.list_tools()) == 1

    tool_registry.clear()

    assert len(tool_registry.list_tools()) == 0


@pytest.mark.asyncio
async def test_tool_handler_execution(tool_registry):
    """Test that tool handler can be executed."""
    params: Dict[str, Any] = {"type": "object", "properties": {}}
    handler = create_mock_handler("test_handler")

    tool_registry.register("data", ToolDefinition(
        name="test_handler_tool",
        description="Test handler",
        parameters=params,
        handler=handler,
    ))

    tool = tool_registry.get_tool("data:test_handler_tool")
    assert tool.handler is not None

    result = await tool.handler()
    assert result == "result from test_handler"


def test_predefined_tools_registered():
    """Test that all predefined tools are registered."""
    registry = ToolRegistry()
    registry.register_predefined_tools()

    expected_tools = [
        "market:check_db_status",
        "market:get_table_names",
        "market:get_ticker_info",
        "data:fetch_stock_price",
        "data:save_ohlcv",
        "data:fetch_company_fundamentals",
        "analysis:run_fundamental_scan",
        "analysis:run_technical_scan",
    ]

    for tool_name in expected_tools:
        tool = registry.get_tool(tool_name)
        assert tool is not None, f"Tool {tool_name} not found in registry"
