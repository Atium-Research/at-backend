# at-backend

FastAPI backend with a lightweight Claude Agent (Claude Agent SDK). Designed to be called by a Next.js BFF: Next.js handles UI + auth and proxies agent requests here.

## Project layout

- **`agent/`** – Agent runner and options. `runner.run_agent()` runs a single turn; options can be extended here (e.g. system prompt, model).
- **`skills/`** – Custom tools and optional Agent Skill config. Add modules that use `@tool` and `create_sdk_mcp_server`, then wire them in `skills/__init__.py` via `get_agent_options_overrides()` so the agent gets `mcp_servers` and `allowed_tools` without hardcoding in the runner.
- **`main.py`** – FastAPI app, CORS, and routes (e.g. POST /agent/chat).

Optional later: **`routes/`** (split by domain), **`config/`** (pydantic-settings), **`models/`** (Pydantic schemas shared across routes).

## Setup

```bash
uv sync
cp .env.example .env   # add ANTHROPIC_API_KEY if your environment needs it
```

## Run

```bash
uv run python main.py
```

- API: http://localhost:8000  
- Docs: http://localhost:8000/docs  

## Agent API

- **POST /agent/chat** — single-turn chat. Body: `{ "message": "..." }`. Returns `{ "response": "..." }`.

From Next.js (BFF or server action), call this endpoint; keep API keys and agent state on the backend. Add Postgres/Redis later for conversation history and job status if needed.
