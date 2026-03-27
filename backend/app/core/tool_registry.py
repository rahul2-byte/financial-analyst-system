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

        tools = [
            ("market", "check_db_status", "Check database status"),
            ("market", "get_table_names", "Get table names"),
            ("market", "get_ticker_info", "Get ticker information"),
            ("data", "fetch_stock_price", "Fetch stock price data"),
            ("data", "save_ohlcv", "Save OHLCV data"),
            ("data", "fetch_company_fundamentals", "Fetch company fundamentals"),
            ("analysis", "run_fundamental_scan", "Run fundamental analysis scan"),
            ("analysis", "run_technical_scan", "Run technical analysis scan"),
        ]

        for namespace, name, desc in tools:
            self.register(
                namespace,
                ToolDefinition(
                    name=name,
                    description=desc,
                    parameters=params_empty,
                    handler=noop_handler,
                ),
            )


def _register_predefined_tools() -> None:
    registry = ToolRegistry()
    registry.clear()
    registry.register_predefined_tools()


_register_predefined_tools()
