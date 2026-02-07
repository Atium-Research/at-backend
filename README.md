# at-backend

Long-lived chat with a Claude agent. Frontend connects over WebSocket; one agent per chat. Chats and messages are in-memory by default; set `DATABASE_URL` for PostgreSQL persistence.

## Layout

- **main.py** — FastAPI app: chat store, session (agent + subscribers), REST + WebSocket.
- **agent.py** — `AgentSession`: queue-fed agent that streams replies (one per chat).
- **db.py** — PostgreSQL store (used when `DATABASE_URL` is set).
- **schema.sql** — Table definitions for `chats` and `chat_messages`.

## Run

```bash
uv sync
uv run python main.py
```

### PostgreSQL (optional)

To persist chats and messages:

1. Create a database and set the connection string:
   ```bash
   export DATABASE_URL="postgresql://user:password@localhost:5432/at_backend"
   ```

2. Create tables (once). Either run the schema manually:
   ```bash
   psql "$DATABASE_URL" -f schema.sql
   ```
   Or start the app—it runs `schema.sql` on startup when `DATABASE_URL` is set.

3. Start the app; it will use Postgres instead of in-memory storage.

- API: http://localhost:8000
- WebSocket: ws://localhost:8000/ws

## Frontend flow

1. **Create a chat** — `POST /api/chats` → get `{ id, title, ... }`.
2. **Connect** — Open WebSocket to `/ws`.
3. **Subscribe** — Send `{ "type": "subscribe", "chatId": "<id>" }` → server sends `{ "type": "history", "messages": [...] }`.
4. **Send a message** — Send `{ "type": "chat", "chatId": "<id>", "content": "..." }` → server broadcasts `user_message`, then `assistant_message` / `tool_use` / `result` / `error` as the agent responds.

REST: `GET /api/chats`, `GET /api/chats/{id}`, `GET /api/chats/{id}/messages`, `DELETE /api/chats/{id}`.
