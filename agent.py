"""
Long-lived chat agent: one queue-fed query() stream per session.
Frontend connects via WebSocket; each chat has one AgentSession.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

SYSTEM_PROMPT = """You are a helpful AI assistant. Be concise but thorough."""


class AgentSession:
    """One long-running query() that reads user messages from a queue and streams events out."""

    def __init__(self) -> None:
        self._input_queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._output_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    def _prompt_stream(self) -> AsyncIterator[dict[str, Any]]:
        async def _stream() -> AsyncIterator[dict[str, Any]]:
            while not self._closed:
                content = await self._input_queue.get()
                if content is None:
                    return
                yield {
                    "type": "user",
                    "message": {"role": "user", "content": content},
                    "parent_tool_use_id": None,
                    "session_id": "",
                }

        return _stream()

    async def _run_query(self) -> None:
        options = ClaudeAgentOptions(
            model="claude-opus-4-6",
            system_prompt=SYSTEM_PROMPT,
            max_turns=100,
            allowed_tools=[
                "Bash",
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep",
                "WebSearch",
                "WebFetch",
                "Computer",
            ],
        )
        try:
            async for msg in query(prompt=self._prompt_stream(), options=options):
                if self._closed:
                    break
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            self._output_queue.put_nowait(
                                {"type": "assistant_message", "content": block.text}
                            )
                        elif isinstance(block, ToolUseBlock):
                            self._output_queue.put_nowait(
                                {
                                    "type": "tool_use",
                                    "toolName": block.name,
                                    "toolId": block.id,
                                    "toolInput": block.input,
                                }
                            )
                elif isinstance(msg, ResultMessage):
                    self._output_queue.put_nowait(
                        {
                            "type": "result",
                            "success": not getattr(msg, "is_error", True),
                            "cost": getattr(msg, "total_cost_usd", None),
                            "duration_ms": getattr(msg, "duration_ms", 0),
                        }
                    )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if not self._closed:
                self._output_queue.put_nowait({"type": "error", "error": str(e)})
        finally:
            self._output_queue.put_nowait(None)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run_query())

    def send_message(self, content: str) -> None:
        self.start()
        self._input_queue.put_nowait(content)

    async def get_output_stream(self) -> AsyncIterator[dict[str, Any]]:
        self.start()
        while True:
            msg = await self._output_queue.get()
            if msg is None:
                break
            yield msg

    def close(self) -> None:
        self._closed = True
        self._input_queue.put_nowait(None)
        if self._task and not self._task.done():
            self._task.cancel()
