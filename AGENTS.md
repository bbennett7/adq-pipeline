# adq-pipeline

Python/FastAPI service for daily question generation at askdumbquestions.ai. Deployed on Fly.io.

## Commands

- `uv run uvicorn app.main:app --reload` — run dev server
- `uv run pytest` — run tests
- `uv run ruff check .` — lint
- `uv run ruff format .` — format

## Architecture

- `app/main.py` — FastAPI app with lifespan (scheduler + db pool)
- `app/routes/` — HTTP endpoints (run, generate, style, choose, retrieve-resources, health)
- `app/services/` — business logic (pipeline orchestration, generation, review, styling, resources, publisher, notifications)
- `app/clients/` — external API wrappers (Ground Ctrl, Anthropic, OpenAI, Gemini, OneSignal, Reddit)
- `app/models/` — Pydantic models
- `app/cron/` — APScheduler jobs (6am, 8:45am, 9am PT)
- `app/config.py` — settings from env vars
- `app/db.py` — asyncpg pool (read-only)
- `app/auth.py` — shared secret bearer auth
- `app/dates.py` — PT/UTC date utilities

## Conventions

- Pipeline never writes to DB directly — all mutations go through Ground Ctrl HTTP API
- DB reads are for auto-publish logic only
- All times PT, all timestamps stored as UTC
- Auth: symmetric `PIPELINE_SECRET` bearer token
- Soft deletes everywhere: filter `WHERE deleted_at IS NULL`
