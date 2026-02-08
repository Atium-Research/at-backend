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

---

## Research project (New Research Project)

Starts the Research Project Agent (marimo notebook, atium-research GitHub repo) and streams progress over the **same** WebSocket, using the same event types as chat.

### 1. Prepare the chat

- Create a chat: `POST /api/chats` → get `{ id, ... }`.
- Open WebSocket to `/ws`.
- Subscribe: send `{ "type": "subscribe", "chatId": "<id>" }` and handle `{ "type": "history", "messages": [...] }`.

### 2. Start research

Send one message:

```json
{
  "type": "research",
  "chatId": "<uuid>",
  "topic": "Short Term Reversal",
  "repo_name": "at-research-reversal-1"
}
```

- **`chatId`** — Same chat id you subscribed to (required).
- **`topic`** — Research topic / signal name (required).
- **`repo_name`** — Optional. If omitted or `null`, the backend derives a name from the topic (e.g. slug).

### 3. Handle events

The server streams events for that **chatId** on the same WebSocket. Handle them like normal chat:

| `type`            | Meaning                    | Payload |
|-------------------|----------------------------|--------|
| `assistant_message` | Agent text (streamed)     | `content`, `chatId` |
| `agent_status`    | Status line                | `message`, `chatId` (e.g. "Running a command", "Reading a file") |
| `tool_use`        | Agent is using a tool      | `toolName`, `toolId`, `toolInput`, `chatId` |
| `result`          | Turn finished              | `success`, `chatId`, optional `cost`, `duration_ms` |
| `error`           | Something failed           | `error`, `chatId` |

Append `assistant_message` to the chat UI; show `agent_status` as a transient status; use `result` to clear loading; show `error` and stop.

### 4. Example (frontend)

```ts
// After subscribe and storing chatId
function startResearch(topic: string, repoName?: string | null) {
  ws.send(JSON.stringify({
    type: "research",
    chatId,
    topic,
    repo_name: repoName ?? null,
  }));
}

// In ws.onmessage (same handler as chat)
const data = JSON.parse(event.data);
if (data.type === "assistant_message") appendMessage(data.chatId, "assistant", data.content);
if (data.type === "agent_status") setStatus(data.message);
if (data.type === "result") setStatus(null);
if (data.type === "error") showError(data.error);
```

### If you get "Invalid message format"

1. **Send exactly one JSON object per WebSocket message**  
   One `ws.send(JSON.stringify({...}))` per user action. Do not concatenate two JSON objects in one send, and do not send an extra message (e.g. a second subscribe) when you receive `history`.

2. **Use the correct keys**  
   The research payload must be a single object with:
   - `type`: string `"research"` (backend accepts any case and trims whitespace).
   - `chatId`: string (same id you used in subscribe).
   - `topic`: string (required).
   - `repo_name`: string or `null` (optional).

3. **Wait for subscribe to complete before sending research**  
   Send `research` only after you’ve sent `subscribe` and (optionally) handled `history`. If you send `research` in the same tick as `subscribe`, that’s fine; the backend processes one message at a time. Avoid sending a third message (e.g. another subscribe or a heartbeat) immediately after `research` unless it has a known `type`.

4. **Check backend logs**  
   If the backend doesn’t recognize the message, it logs: `WebSocket unknown message type: ... (keys: ...)`. That shows what `type` and keys were received so you can fix the payload.
