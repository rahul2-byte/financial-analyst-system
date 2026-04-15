import asyncio
import logging
from typing import Dict, Any, List, Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from app.config import settings

logger = logging.getLogger(__name__)


class MCPManager:
    """Manages long-lived MCP connections for PostgreSQL and Qdrant."""

    def __init__(self):
        self._exit_stack = AsyncExitStack()
        self.sessions: Dict[str, ClientSession] = {}
        self.tool_definitions = []
        self._mcp_tool_map: Dict[str, str] = {}  # Map full tool name to MCP server name

    async def start(self):
        """Initializes MCP server connections."""
        try:
            # PostgreSQL MCP
            pg_url = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
            pg_params = StdioServerParameters(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-postgres", pg_url],
            )
            await self._connect("postgres", pg_params)

            # Note: We can add Qdrant MCP here when ready, or wrap our Qdrant instance.
            # For now we'll start with postgres to validate.

            logger.info("MCP Servers initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize MCP servers: {e}")

    async def _connect(self, name: str, params: StdioServerParameters):
        try:
            stdio_transport = await self._exit_stack.enter_async_context(
                stdio_client(params)
            )
            read, write = stdio_transport
            session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()
            self.sessions[name] = session

            # Fetch and cache tools
            mcp_tools = await session.list_tools()
            for t in mcp_tools.tools:
                # Store full tool name mapping
                full_name = f"mcp_{name}:{t.name}"
                self._mcp_tool_map[full_name] = name

                # Convert MCP Tool to our ToolDefinition format
                from app.core.tools.tool_system import (
                    ToolDefinition,
                    ToolNamespace,
                    tool_registry,
                )

                # Create a custom namespace if needed or reuse RESEARCH
                tool_def = ToolDefinition(
                    name=t.name,
                    description=t.description or "MCP Tool",
                    parameters=t.inputSchema,
                    namespace=ToolNamespace.RESEARCH,  # Temporarily reuse RESEARCH
                )
                # Override the full name to be unique
                tool_def.name = f"{name}_{t.name}"

                self.tool_definitions.append(tool_def)
                tool_registry.register(tool_def)

                # Register a generic handler in tool_executor
                from app.core.tools.tool_system import tool_executor

                def make_handler(srv_name: str, t_name: str):
                    async def mcp_handler(args):
                        return await self.call_tool(srv_name, t_name, args)

                    return mcp_handler

                tool_executor.register_handler(
                    tool_def.full_name, make_handler(name, t.name)
                )

            logger.info(
                f"Connected to MCP server: {name} and loaded {len(mcp_tools.tools)} tools."
            )
        except Exception as e:
            logger.error(f"Error connecting to MCP server {name}: {e}")

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        if server_name not in self.sessions:
            raise ValueError(f"MCP server {server_name} not connected.")
        session = self.sessions[server_name]
        try:
            result = await session.call_tool(tool_name, arguments)
            # Format result
            if result.isError:
                return {"error": str(result.content)}

            # The result.content is a list of CallToolResult objects (text, image, etc.)
            return {"result": [c.text for c in result.content if hasattr(c, "text")]}
        except Exception as e:
            logger.error(f"Error calling MCP tool {tool_name} on {server_name}: {e}")
            return {"error": str(e)}

    async def close(self):
        """Close all MCP connections."""
        await self._exit_stack.aclose()
        self.sessions.clear()


mcp_manager = MCPManager()
