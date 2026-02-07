"""
Agent runner: runs a single turn via Claude Agent SDK query().
Options (system prompt, tools) are built here; tools come from skills.
"""
from __future__ import annotations

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

from skills import get_agent_options_overrides


async def run_agent(
    message: str,
    *,
    system_prompt: str | None = None,
    max_turns: int | None = None,
) -> str:
    options = ClaudeAgentOptions(
        system_prompt=system_prompt or "You are a helpful assistant.",
        max_turns=max_turns or 10,
        **get_agent_options_overrides(),
    )
    text_parts: list[str] = []
    async for msg in query(prompt=message, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
    return "\n".join(text_parts).strip() if text_parts else ""
