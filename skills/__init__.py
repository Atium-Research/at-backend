"""
Skills: custom tools and optional Agent Skill config for the Claude agent.

- Add modules here that define tools with @tool and create_sdk_mcp_server.
- Export get_agent_options_overrides() so the agent runner can wire in
  mcp_servers and allowed_tools without hardcoding them in the runner.
"""
from __future__ import annotations

from typing import Any


def get_agent_options_overrides() -> dict[str, Any]:
    """
    Overrides to pass into ClaudeAgentOptions (e.g. mcp_servers, allowed_tools).
    Import skill modules and build the dict here so the agent stays unaware of
    individual skill names.
    """
    # Example once you add a skill with create_sdk_mcp_server:
    # from skills.example import sdk_server, ALLOWED_TOOLS
    # return {"mcp_servers": {"example": sdk_server}, "allowed_tools": ALLOWED_TOOLS}
    return {}
