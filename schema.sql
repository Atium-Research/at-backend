-- Chat persistence for at-backend. Run once: psql $DATABASE_URL -f schema.sql
-- Or use init_db() in db.py on app startup.

CREATE TABLE IF NOT EXISTS chats (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT 'New Chat',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          TEXT PRIMARY KEY,
    chat_id     TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_id ON chat_messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON chats(updated_at DESC);
