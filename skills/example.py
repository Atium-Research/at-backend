"""
Example skill: defines a custom tool and an SDK MCP server.

To enable:
  1. In skills/__init__.py, import this module and add sdk_server and
     ALLOWED_TOOLS to get_agent_options_overrides().
  2. Uncomment the return dict in get_agent_options_overrides() and wire:
     mcp_servers={"example": sdk_server}, allowed_tools=ALLOWED_TOOLS
"""
from __future__ import annotations

from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool


@tool("greet", "Greet someone by name", {"name": str})
async def greet(args: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"Hello, {args['name']}!"}]}


sdk_server = create_sdk_mcp_server(
    name="example",
    version="1.0.0",
    tools=[greet],
)
ALLOWED_TOOLS = ["mcp__example__greet"]
