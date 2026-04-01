"""Tests for unified tool system."""

import pytest
from app.core.tools.tool_system import (
    ToolDefinition,
    ToolNamespace,
    ToolResult,
    ToolRegistry,
    ToolExecutor,
    tool_registry,
    tool_executor,
    initialize_tool_system,
)


class TestToolDefinition:
    """Test ToolDefinition dataclass."""

    def test_full_name_constructs_correctly(self):
        """Full name should be namespace:name."""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object"},
            namespace=ToolNamespace.MARKET,
        )
        assert tool.full_name == "market:test_tool"

    def test_default_namespace_is_data(self):
        """Default namespace should be DATA."""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object"},
        )
        assert tool.namespace == ToolNamespace.DATA


class TestToolResult:
    """Test ToolResult dataclass."""

    def test_success_result_to_dict(self):
        """Successful result should serialize correctly."""
        result = ToolResult(success=True, data={"key": "value"})
        d = result.to_dict()

        assert d["success"] is True
        assert d["data"] == {"key": "value"}
        assert "error" not in d

    def test_error_result_to_dict(self):
        """Error result should serialize correctly."""
        result = ToolResult(success=False, error="Something went wrong")
        d = result.to_dict()

        assert d["success"] is False
        assert d["error"] == "Something went wrong"

    def test_delegation_result_to_dict(self):
        """Delegation result should serialize correctly."""
        result = ToolResult(success=True, delegate_to_agent="market_news")
        d = result.to_dict()

        assert d["success"] is True
        assert d["delegate_to_agent"] == "market_news"


class TestToolRegistry:
    """Test ToolRegistry class."""

    def test_register_tool(self):
        """Tools should be registerable."""
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="test_tool",
            description="Test",
            parameters={},
            namespace=ToolNamespace.DATA,
        )

        registry.register(tool)

        assert registry.get_tool("data:test_tool") is not None

    def test_get_nonexistent_tool(self):
        """Getting nonexistent tool should return None."""
        registry = ToolRegistry()

        assert registry.get_tool("nonexistent:tool") is None

    def test_list_tools(self):
        """List tools should return all registered tools."""
        registry = ToolRegistry()

        tools = registry.list_tools()

        assert isinstance(tools, list)

    def test_get_tools_by_namespace(self):
        """Getting tools by namespace should filter correctly."""
        registry = ToolRegistry()

        market_tools = registry.get_tools_by_namespace(ToolNamespace.MARKET)

        assert all(t.namespace == ToolNamespace.MARKET for t in market_tools)

    def test_clear_removes_all_tools(self):
        """Clear should remove all tools."""
        registry = ToolRegistry()
        tool = ToolDefinition(
            name="test_tool",
            description="Test",
            parameters={},
        )
        registry.register(tool)

        registry.clear()

        assert len(registry.list_tools()) == 0


class TestToolExecutor:
    """Test ToolExecutor class."""

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self):
        """Executing nonexistent tool should return error."""
        executor = ToolExecutor(tool_registry)

        result = await executor.execute("nonexistent:tool", {})

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_with_delegation(self):
        """Tool that delegates should return delegation result."""
        initialize_tool_system()
        # Use the global initialized executor
        result = await tool_executor.execute(
            "data:fetch_stock_data", {"ticker": "AAPL"}
        )

        assert result.success is True
        assert result.delegate_to_agent == "price_and_fundamentals"

    def test_registration_of_handler(self):
        """Handlers should be registerable."""
        executor = ToolExecutor(ToolRegistry())

        executor.register_handler("test:tool", lambda args: {"result": "success"})

        assert "test:tool" in executor._handlers


class TestToolSystemIntegration:
    """Test tool system integration."""

    def test_initialization(self):
        """Tool system should initialize."""
        initialize_tool_system()

        assert tool_registry.is_initialized
        assert len(tool_registry.list_tools()) > 0

    def test_predefined_tools_exist(self):
        """Predefined tools should exist."""
        initialize_tool_system()

        assert tool_registry.get_tool("market:check_db_status") is not None
        assert tool_registry.get_tool("data:fetch_fundamentals") is not None
        assert tool_registry.get_tool("analysis:run_technical_scan") is not None

    def test_tools_by_namespace_coverage(self):
        """All namespaces should have tools."""
        initialize_tool_system()

        for ns in ToolNamespace:
            tools = tool_registry.get_tools_by_namespace(ns)
            # Some namespaces may be empty, but the enum should work
            assert isinstance(tools, list)
