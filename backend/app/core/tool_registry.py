from typing import Any, Dict, Optional, Callable, List
from pydantic import BaseModel


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Optional[Callable] = None


class ToolRegistry:
    _instance: Optional["ToolRegistry"] = None
    _tools: Dict[str, ToolDefinition] = {}

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._tools = {}
        return cls._instance

    def register(self, namespace: str, tool: ToolDefinition) -> None:
        full_name = f"{namespace}:{tool.name}"
        self._tools[full_name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def clear(self) -> None:
        self._tools.clear()

    def register_predefined_tools(self) -> None:
        params_empty = {"type": "object", "properties": {}}

        async def noop_handler(*args, **kwargs):
            pass

        self.register("market", ToolDefinition(
            name="check_db_status",
            description="Check database status",
            parameters=params_empty,
            handler=noop_handler,
        ))
        self.register("market", ToolDefinition(
            name="get_table_names",
            description="Get table names",
            parameters=params_empty,
            handler=noop_handler,
        ))
        self.register("market", ToolDefinition(
            name="get_ticker_info",
            description="Get ticker information",
            parameters=params_empty,
            handler=noop_handler,
        ))

        self.register("data", ToolDefinition(
            name="fetch_stock_price",
            description="Fetch stock price data",
            parameters=params_empty,
            handler=noop_handler,
        ))
        self.register("data", ToolDefinition(
            name="save_ohlcv",
            description="Save OHLCV data",
            parameters=params_empty,
            handler=noop_handler,
        ))
        self.register("data", ToolDefinition(
            name="fetch_company_fundamentals",
            description="Fetch company fundamentals",
            parameters=params_empty,
            handler=noop_handler,
        ))

        self.register("analysis", ToolDefinition(
            name="run_fundamental_scan",
            description="Run fundamental analysis scan",
            parameters=params_empty,
            handler=noop_handler,
        ))
        self.register("analysis", ToolDefinition(
            name="run_technical_scan",
            description="Run technical analysis scan",
            parameters=params_empty,
            handler=noop_handler,
        ))


def _register_predefined_tools() -> None:
    registry = ToolRegistry()
    registry.clear()

    params_empty = {"type": "object", "properties": {}}

    async def noop_handler(*args, **kwargs):
        pass

    registry.register("market", ToolDefinition(
        name="check_db_status",
        description="Check database status",
        parameters=params_empty,
        handler=noop_handler,
    ))
    registry.register("market", ToolDefinition(
        name="get_table_names",
        description="Get table names",
        parameters=params_empty,
        handler=noop_handler,
    ))
    registry.register("market", ToolDefinition(
        name="get_ticker_info",
        description="Get ticker information",
        parameters=params_empty,
        handler=noop_handler,
    ))

    registry.register("data", ToolDefinition(
        name="fetch_stock_price",
        description="Fetch stock price data",
        parameters=params_empty,
        handler=noop_handler,
    ))
    registry.register("data", ToolDefinition(
        name="save_ohlcv",
        description="Save OHLCV data",
        parameters=params_empty,
        handler=noop_handler,
    ))
    registry.register("data", ToolDefinition(
        name="fetch_company_fundamentals",
        description="Fetch company fundamentals",
        parameters=params_empty,
        handler=noop_handler,
    ))

    registry.register("analysis", ToolDefinition(
        name="run_fundamental_scan",
        description="Run fundamental analysis scan",
        parameters=params_empty,
        handler=noop_handler,
    ))
    registry.register("analysis", ToolDefinition(
        name="run_technical_scan",
        description="Run technical analysis scan",
        parameters=params_empty,
        handler=noop_handler,
    ))


_register_predefined_tools()
