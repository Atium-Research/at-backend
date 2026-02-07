# at-backend

Long-lived chat with a Claude agent. Frontend connects over WebSocket; one agent per chat, in-memory history.

## Layout

- **main.py** — FastAPI app: chat store, session (agent + subscribers), REST + WebSocket.
- **agent.py** — `AgentSession`: queue-fed agent that streams replies (one per chat).

## Run

```bash
uv sync
uv run python main.py
```

- API: http://localhost:8000
- WebSocket: ws://localhost:8000/ws

## Frontend flow

1. **Create a chat** — `POST /api/chats` → get `{ id, title, ... }`.
2. **Connect** — Open WebSocket to `/ws`.
3. **Subscribe** — Send `{ "type": "subscribe", "chatId": "<id>" }` → server sends `{ "type": "history", "messages": [...] }`.
4. **Send a message** — Send `{ "type": "chat", "chatId": "<id>", "content": "..." }` → server broadcasts `user_message`, then `assistant_message` / `tool_use` / `result` / `error` as the agent responds.

REST: `GET /api/chats`, `GET /api/chats/{id}`, `GET /api/chats/{id}/messages`, `DELETE /api/chats/{id}`.
