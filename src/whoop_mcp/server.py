"""MCP stdio server entry point for the Whoop integration."""

from __future__ import annotations

import asyncio
import logging
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from . import __version__
from .tools import TOOL_DEFINITIONS

logger = logging.getLogger(__name__)


def _build_server() -> Server:
    server: Server = Server("whoop-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["inputSchema"],
            )
            for t in TOOL_DEFINITIONS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        for t in TOOL_DEFINITIONS:
            if t["name"] == name:
                handler = t["handler"]
                try:
                    result = await handler(**(arguments or {}))
                except Exception as e:  # noqa: BLE001
                    logger.exception("tool %s failed", name)
                    return [TextContent(type="text", text=f"ERROR: {type(e).__name__}: {e}")]
                return [TextContent(type="text", text=result)]
        return [TextContent(type="text", text=f"ERROR: unknown tool {name}")]

    return server


async def _run() -> None:
    server = _build_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    """Console-script entry point declared in pyproject.toml."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    logger.info("Starting whoop-mcp server v%s", __version__)
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
