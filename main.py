"""
FastAPI app: long-lived chat over WebSocket.
- REST: create chat, list chats, get messages.
- WebSocket /ws: subscribe to a chat, send messages, receive streamed replies.
- Set DATABASE_URL for PostgreSQL persistence; otherwise in-memory.
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()  # load .env before reading os.environ
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import AgentSession


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging

    global chat_store
    logger = logging.getLogger("uvicorn.error")
    using_postgres = False
    if os.environ.get("DATABASE_URL"):
        try:
            from db import close_pool, get_pool, init_db, PostgresChatStore

            pool = await get_pool()
            await init_db(pool)
            chat_store = PostgresChatStore(pool)
            using_postgres = True
            logger.info("Using PostgreSQL for chat persistence")
        except Exception as e:
            logger.warning(
                "Could not connect to PostgreSQL (%s). Using in-memory store. "
                "Check DATABASE_URL: use postgresql://user:pass@host:5432/dbname (host must resolve, e.g. localhost or your DB host).",
                e,
            )
            chat_store = InMemoryChatStore()
    try:
        yield
    finally:
        if using_postgres:
            try:
                from db import close_pool

                await close_pool()
            except Exception:
                pass


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://atiumresearch.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class ChatStoreProtocol(Protocol):
    async def create_chat(self, title: str | None = None) -> Chat: ...
    async def get_chat(self, chat_id: str) -> Chat | None: ...
    async def get_all_chats(self) -> list[Chat]: ...
    async def delete_chat(self, chat_id: str) -> bool: ...
    async def add_message(
        self, chat_id: str, role: str, content: str
    ) -> ChatMessage: ...
    async def get_messages(self, chat_id: str) -> list[ChatMessage]: ...


class InMemoryChatStore:
    """In-memory chat store (async interface for compatibility with Postgres store)."""

    def __init__(self) -> None:
        self._chats: dict[str, Chat] = {}
        self._messages: dict[str, list[ChatMessage]] = {}

    async def create_chat(self, title: str | None = None) -> Chat:
        chat_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        chat = Chat(
            id=chat_id, title=title or "New Chat", created_at=now, updated_at=now
        )
        self._chats[chat_id] = chat
        self._messages[chat_id] = []
        return chat

    async def get_chat(self, chat_id: str) -> Chat | None:
        return self._chats.get(chat_id)

    async def get_all_chats(self) -> list[Chat]:
        return sorted(self._chats.values(), key=lambda c: c.updated_at, reverse=True)

    async def delete_chat(self, chat_id: str) -> bool:
        self._messages.pop(chat_id, None)
        return self._chats.pop(chat_id, None) is not None

    async def add_message(self, chat_id: str, role: str, content: str) -> ChatMessage:
        if chat_id not in self._messages:
            raise ValueError(f"Chat {chat_id} not found")
        now = datetime.now(timezone.utc).isoformat()
        msg = ChatMessage(
            id=uuid.uuid4().hex,
            chat_id=chat_id,
            role=role,
            content=content,
            timestamp=now,
        )
        self._messages[chat_id].append(msg)
        chat = self._chats.get(chat_id)
        if chat:
            chat.updated_at = msg.timestamp
            if chat.title == "New Chat" and role == "user":
                chat.title = content[:50] + ("..." if len(content) > 50 else "")
        return msg

    async def get_messages(self, chat_id: str) -> list[ChatMessage]:
        return self._messages.get(chat_id, [])


# Set in lifespan; use InMemoryChatStore() until then for type hints
chat_store: ChatStoreProtocol = InMemoryChatStore()

# Friendly status messages when the agent uses a tool (sent over WebSocket before tool_use)
AGENT_STATUS_BY_TOOL: dict[str, str] = {
    "WebSearch": "Searching the web",
    "WebFetch": "Fetching a page",
    "Read": "Reading a file",
    "Write": "Writing a file",
    "Edit": "Editing a file",
    "Bash": "Running a command",
    "Glob": "Searching for files",
    "Grep": "Searching in files",
}


def _agent_status_message(tool_name: str) -> str:
    return AGENT_STATUS_BY_TOOL.get(tool_name, f"Using {tool_name}")


# --- Session: one chat = one agent + subscribers ---


class Session:
    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id
        self._subscribers: set[Any] = set()
        self._agent = AgentSession()
        self._listening: asyncio.Task[None] | None = None
        self._is_listening = False

    async def _listen(self) -> None:
        if self._is_listening:
            return
        self._is_listening = True
        try:
            async for msg in self._agent.get_output_stream():
                if msg.get("type") == "tool_use":
                    status = _agent_status_message(msg.get("toolName", ""))
                    await self._broadcast(
                        {
                            "type": "agent_status",
                            "message": status,
                            "chatId": self.chat_id,
                        }
                    )
                await self._broadcast(await self._wrap(msg))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            await self._broadcast(
                {"type": "error", "error": str(e), "chatId": self.chat_id}
            )

    async def _wrap(self, msg: dict[str, Any]) -> dict[str, Any]:
        out = {**msg, "chatId": self.chat_id}
        if msg.get("type") == "assistant_message":
            await chat_store.add_message(
                self.chat_id, "assistant", msg.get("content", "")
            )
        return out

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        dead = []
        for ws in self._subscribers:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for c in dead:
            self._subscribers.discard(c)

    async def send_message(self, content: str) -> None:
        await chat_store.add_message(self.chat_id, "user", content)
        asyncio.create_task(
            self._broadcast(
                {"type": "user_message", "content": content, "chatId": self.chat_id}
            )
        )
        self._agent.send_message(content)
        if not self._is_listening and self._listening is None:
            self._listening = asyncio.create_task(self._listen())

    def subscribe(self, ws: Any) -> None:
        self._subscribers.add(ws)

    def unsubscribe(self, ws: Any) -> None:
        self._subscribers.discard(ws)

    def close(self) -> None:
        self._agent.close()
        if self._listening and not self._listening.done():
            self._listening.cancel()


sessions: dict[str, Session] = {}


def get_session(chat_id: str) -> Session:
    if chat_id not in sessions:
        sessions[chat_id] = Session(chat_id)
    return sessions[chat_id]


# --- REST ---


class CreateChatBody(BaseModel):
    title: str | None = None


@app.get("/")
def root():
    return {"message": "Hello from at-backend!"}


@app.get("/api/chats")
async def list_chats():
    return await chat_store.get_all_chats()


@app.post("/api/chats", status_code=201)
async def create_chat(body: CreateChatBody | None = None):
    return await chat_store.create_chat(title=body.title if body else None)


@app.get("/api/chats/{chat_id}")
async def get_chat(chat_id: str):
    chat = await chat_store.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str):
    if not await chat_store.delete_chat(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    if chat_id in sessions:
        sessions[chat_id].close()
        del sessions[chat_id]
    return {"success": True}


@app.get("/api/chats/{chat_id}/messages")
async def get_messages(chat_id: str):
    return await chat_store.get_messages(chat_id)


# --- WebSocket ---


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json(
        {"type": "connected", "message": "Connected to chat server"}
    )
    try:
        while True:
            data = await websocket.receive_json()
            t = data.get("type")
            chat_id = data.get("chatId", "")
            if t == "subscribe":
                session = get_session(chat_id)
                session.subscribe(websocket)
                messages = await chat_store.get_messages(chat_id)
                await websocket.send_json(
                    {"type": "history", "messages": messages, "chatId": chat_id}
                )
            elif t == "chat":
                session = get_session(chat_id)
                session.subscribe(websocket)
                await session.send_message(data.get("content", ""))
            else:
                await websocket.send_json(
                    {"type": "error", "error": "Invalid message format"}
                )
    except WebSocketDisconnect:
        pass
    finally:
        for s in sessions.values():
            s.unsubscribe(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
