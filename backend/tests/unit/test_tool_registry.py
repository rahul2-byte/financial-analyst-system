from collections.abc import Callable
from typing import Any

import pytest
from app.core.tools.tool_system import ToolDefinition, ToolNamespace, ToolRegistry


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


def test_tool_definition_dataclass():
    """Test ToolDefinition dataclass creation."""
    params: dict[str, Any] = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
    }
    handler = create_mock_handler("test_tool")

    tool = ToolDefinition(
        name="test_tool",
        description="A test tool",
        parameters=params,
        handler=handler,
        namespace=ToolNamespace.DATA,
    )

    assert tool.name == "test_tool"
    assert tool.description == "A test tool"
    assert tool.parameters == params
    assert tool.handler is not None
    assert tool.full_name == "data:test_tool"


def test_tool_definition_optional_handler():
    """Test ToolDefinition can be created without handler."""
    tool = ToolDefinition(
        name="no_handler_tool",
        description="A tool without handler",
        parameters={"type": "object"},
    )

    assert tool.name == "no_handler_tool"
    assert tool.handler is None


def test_tool_definition_default_namespace():
    """Test ToolDefinition defaults to DATA namespace."""
    tool = ToolDefinition(
        name="test",
        description="Test",
        parameters={"type": "object"},
    )

    assert tool.namespace == ToolNamespace.DATA
    assert tool.full_name == "data:test"


def test_register_tool(tool_registry):
    """Test tool registration."""
    params: dict[str, Any] = {"type": "object", "properties": {}}
    handler = create_mock_handler("market_health")

    tool_registry.register(
        ToolDefinition(
            name="market_health",
            description="Check market-data provider status",
            parameters=params,
            handler=handler,
            namespace=ToolNamespace.MARKET,
        ),
    )

    tools = tool_registry.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "market_health"


def test_register_multiple_tools_same_namespace(tool_registry):
    """Test registering multiple tools in the same namespace."""
    params: dict[str, Any] = {"type": "object", "properties": {}}

    tool_registry.register(
        ToolDefinition(
            name="market_health",
            description="Check market-data provider status",
            parameters=params,
            namespace=ToolNamespace.MARKET,
        ),
    )
    tool_registry.register(
        ToolDefinition(
            name="list_market_fields",
            description="List available market fields",
            parameters=params,
            namespace=ToolNamespace.MARKET,
        ),
    )

    tools = tool_registry.list_tools()
    assert len(tools) == 2


def test_register_different_namespaces(tool_registry):
    """Test registering tools in different namespaces."""
    params: dict[str, Any] = {"type": "object", "properties": {}}

    tool_registry.register(
        ToolDefinition(
            name="market_health",
            description="Check market-data provider status",
            parameters=params,
            namespace=ToolNamespace.MARKET,
        ),
    )
    tool_registry.register(
        ToolDefinition(
            name="fetch_stock_price",
            description="Fetch stock price",
            parameters=params,
            namespace=ToolNamespace.DATA,
        ),
    )
    tool_registry.register(
        ToolDefinition(
            name="run_fundamental_scan",
            description="Run fundamental scan",
            parameters=params,
            namespace=ToolNamespace.ANALYSIS,
        ),
    )

    tools = tool_registry.list_tools()
    assert len(tools) == 3


def test_get_tool_by_name(tool_registry):
    """Test retrieving a tool by its full name with namespace."""
    params: dict[str, Any] = {"type": "object", "properties": {}}
    handler = create_mock_handler("market_health")

    tool_registry.register(
        ToolDefinition(
            name="market_health",
            description="Check market-data provider status",
            parameters=params,
            handler=handler,
            namespace=ToolNamespace.MARKET,
        ),
    )

    tool = tool_registry.get_tool("market:market_health")
    assert tool is not None
    assert tool.name == "market_health"
    assert tool.description == "Check market-data provider status"


def test_get_tool_not_found(tool_registry):
    """Test retrieving a non-existent tool returns None."""
    tool = tool_registry.get_tool("nonexistent:tool")
    assert tool is None


def test_list_tools_returns_all_tools(tool_registry):
    """Test list_tools returns all registered tools."""
    params: dict[str, Any] = {"type": "object", "properties": {}}

    tool_registry.register(
        ToolDefinition(
            name="market_health",
            description="Check market-data provider",
            parameters=params,
            namespace=ToolNamespace.MARKET,
        ),
    )
    tool_registry.register(
        ToolDefinition(
            name="fetch_stock_price",
            description="Fetch price",
            parameters=params,
            namespace=ToolNamespace.DATA,
        ),
    )

    tools = tool_registry.list_tools()
    assert len(tools) == 2
    names = [t.name for t in tools]
    assert "market_health" in names
    assert "fetch_stock_price" in names


def test_clear_removes_all_tools(tool_registry):
    """Test that clear() removes all registered tools."""
    params: dict[str, Any] = {"type": "object", "properties": {}}

    tool_registry.register(
        ToolDefinition(
            name="market_health",
            description="Check market-data provider",
            parameters=params,
            namespace=ToolNamespace.MARKET,
        ),
    )

    assert len(tool_registry.list_tools()) == 1

    tool_registry.clear()

    assert len(tool_registry.list_tools()) == 0


def test_get_tools_by_namespace(tool_registry):
    """Test filtering tools by namespace."""
    params = {"type": "object", "properties": {}}

    tool_registry.register(
        ToolDefinition(
            name="tool1",
            description="T1",
            parameters=params,
            namespace=ToolNamespace.MARKET,
        )
    )
    tool_registry.register(
        ToolDefinition(
            name="tool2",
            description="T2",
            parameters=params,
            namespace=ToolNamespace.DATA,
        )
    )
    tool_registry.register(
        ToolDefinition(
            name="tool3",
            description="T3",
            parameters=params,
            namespace=ToolNamespace.DATA,
        )
    )

    market_tools = tool_registry.get_tools_by_namespace(ToolNamespace.MARKET)
    assert len(market_tools) == 1
    assert market_tools[0].name == "tool1"

    data_tools = tool_registry.get_tools_by_namespace(ToolNamespace.DATA)
    assert len(data_tools) == 2


def test_predefined_tools_registered():
    """Test that all predefined tools are registered."""
    registry = ToolRegistry()
    registry.initialize()

    expected_tools = [
        "market:submit_offline_status",
        "data:fetch_stock_data",
        "data:fetch_fundamentals",
        "data:submit_data_response",
        "news:fetch_news",
        "analysis:run_fundamental_scan",
        "analysis:submit_thesis",
        "analysis:run_technical_scan",
        "interaction:ask_user",
    ]

    for tool_name in expected_tools:
        tool = registry.get_tool(tool_name)
        assert tool is not None, f"Tool {tool_name} not found in registry"
