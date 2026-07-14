# Cobaju backend

This FastAPI service contains Cobaju's Phase 1 backend foundation:

- settings loaded from environment variables or the repository root `.env`;
- a SQLModel engine and per-request session dependency;
- a local SQLite database;
- Alembic migration configuration and an initial revision;
- API and database health checks;
- pytest coverage for settings, sessions, and health routes.

Domain models and authentication intentionally begin in later phases.

## Run from the repository root

Install dependencies and apply migrations:

```bash
uv sync --project apps/backend
moon run backend:migrate
```

Start the API:

```bash
moon run backend:dev
```

Run the backend tests:

```bash
moon run backend:test
```

Native uv commands are also available:

```bash
uv run --project apps/backend alembic -c apps/backend/alembic.ini upgrade head
uv run --project apps/backend pytest apps/backend/tests
uv run --project apps/backend uvicorn --app-dir apps/backend app.main:app --reload
```
