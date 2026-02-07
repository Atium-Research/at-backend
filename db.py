"""
PostgreSQL persistence for chats and messages.
Set DATABASE_URL to enable; otherwise the app uses in-memory store.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL")
print(DATABASE_URL, "DATABASE_URL")


@dataclass
class Chat:
    id: str
    title: str
    created_at: str
    updated_at: str


@dataclass
class ChatMessage:
    id: str
    chat_id: str
    role: str
    content: str
    timestamp: str


_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            command_timeout=60,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def init_db(pool: asyncpg.Pool | None = None) -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    pool = pool or await get_pool()
    schema_path = Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text()
    async with pool.acquire() as conn:
        await conn.execute(sql)


class PostgresChatStore:
    """Chat store backed by PostgreSQL. All methods are async."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_chat(self, title: str | None = None) -> Chat:
        import uuid
        from datetime import datetime, timezone

        chat_id = uuid.uuid4().hex
        title = title or "New Chat"
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO chats (id, title, created_at, updated_at) VALUES ($1, $2, $3, $3)",
                chat_id,
                title,
                now,
            )
        return Chat(
            id=chat_id,
            title=title,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )

    async def get_chat(self, chat_id: str) -> Chat | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, title, created_at, updated_at FROM chats WHERE id = $1",
                chat_id,
            )
        if row is None:
            return None
        return Chat(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"].isoformat(),
            updated_at=row["updated_at"].isoformat(),
        )

    async def get_all_chats(self) -> list[Chat]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, title, created_at, updated_at FROM chats ORDER BY updated_at DESC"
            )
        return [
            Chat(
                id=r["id"],
                title=r["title"],
                created_at=r["created_at"].isoformat(),
                updated_at=r["updated_at"].isoformat(),
            )
            for r in rows
        ]

    async def delete_chat(self, chat_id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM chats WHERE id = $1", chat_id)
        return result == "DELETE 1"

    async def add_message(self, chat_id: str, role: str, content: str) -> ChatMessage:
        import uuid
        from datetime import datetime, timezone

        msg_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO chat_messages (id, chat_id, role, content, timestamp) VALUES ($1, $2, $3, $4, $5)",
                msg_id,
                chat_id,
                role,
                content,
                now,
            )
            await conn.execute(
                "UPDATE chats SET updated_at = $1 WHERE id = $2",
                now,
                chat_id,
            )
            if role == "user":
                row = await conn.fetchrow(
                    "SELECT title FROM chats WHERE id = $1", chat_id
                )
                if row and row["title"] == "New Chat":
                    new_title = content[:50] + ("..." if len(content) > 50 else "")
                    await conn.execute(
                        "UPDATE chats SET title = $1 WHERE id = $2",
                        new_title,
                        chat_id,
                    )
        return ChatMessage(
            id=msg_id,
            chat_id=chat_id,
            role=role,
            content=content,
            timestamp=now.isoformat(),
        )

    async def get_messages(self, chat_id: str) -> list[ChatMessage]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, chat_id, role, content, timestamp FROM chat_messages WHERE chat_id = $1 ORDER BY timestamp",
                chat_id,
            )
        return [
            ChatMessage(
                id=r["id"],
                chat_id=r["chat_id"],
                role=r["role"],
                content=r["content"],
                timestamp=r["timestamp"].isoformat(),
            )
            for r in rows
        ]
